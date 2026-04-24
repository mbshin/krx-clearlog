"""Fixed-width KRX message parser.

Given a registry of schemas, `Parser.parse(raw_bytes)` slices a single
record into typed fields/arrays. Persistence and streaming (multi-record
log files) are layered on top in separate modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from krx_parser.exceptions import FieldDecodeError, UnknownMessageType
from krx_parser.registry import SchemaRegistry, load_default_registry
from krx_parser.schema import Array, Field

# Seq 2 TRANSACTION_CODE starts after MESSAGE_SEQUENCE_NUMBER (Long, 11)
# and is itself 11 bytes. The parser uses this to dispatch before loading
# the full schema.
TRANSACTION_CODE_OFFSET = 11
TRANSACTION_CODE_LENGTH = 11


@dataclass(frozen=True)
class ParsedMessage:
    transaction_code: str
    message_sequence_number: int
    transmit_date: str
    emsg_complt_yn: str
    fields: dict[str, Any] = field(default_factory=dict)
    arrays: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    raw: bytes = b""

    def get(self, name: str, default: Any = None) -> Any:
        return self.fields.get(name, default)


class Parser:
    def __init__(self, registry: SchemaRegistry | None = None) -> None:
        self._registry = registry if registry is not None else load_default_registry()

    @property
    def registry(self) -> SchemaRegistry:
        return self._registry

    def peek_transaction_code(self, raw: bytes) -> str:
        """Extract TRANSACTION_CODE without requiring a full record.

        Useful for streaming input where the caller needs to know the
        record length (from the schema) before slicing.
        """
        if len(raw) < TRANSACTION_CODE_OFFSET + TRANSACTION_CODE_LENGTH:
            raise FieldDecodeError(
                "TRANSACTION_CODE",
                raw,
                f"need at least {TRANSACTION_CODE_OFFSET + TRANSACTION_CODE_LENGTH} bytes",
            )
        slice_ = raw[
            TRANSACTION_CODE_OFFSET : TRANSACTION_CODE_OFFSET + TRANSACTION_CODE_LENGTH
        ]
        return slice_.decode("ascii").strip()

    def record_length(self, transaction_code: str) -> int:
        return self._registry.get(transaction_code).record_length

    def parse(self, raw: bytes) -> ParsedMessage:
        tr_code = self.peek_transaction_code(raw)
        if tr_code not in self._registry:
            raise UnknownMessageType(tr_code)
        schema = self._registry.get(tr_code)

        if len(raw) != schema.record_length:
            raise FieldDecodeError(
                "record",
                raw,
                f"expected {schema.record_length} bytes for {tr_code}, got {len(raw)}",
            )

        fields: dict[str, Any] = {}
        arrays: dict[str, list[dict[str, Any]]] = {}

        for item in schema.layout:
            if isinstance(item, Field):
                fields[item.name] = _decode_field(item, raw, schema.encoding)
            elif isinstance(item, Array):
                arrays[item.name] = _decode_array(item, raw, schema.encoding)

        return ParsedMessage(
            transaction_code=tr_code,
            message_sequence_number=fields["MESSAGE_SEQUENCE_NUMBER"],
            transmit_date=fields["TRANSMIT_DATE"],
            emsg_complt_yn=fields["EMSG_COMPLT_YN"],
            fields=fields,
            arrays=arrays,
            raw=raw,
        )


def parse(raw: bytes, registry: SchemaRegistry | None = None) -> ParsedMessage:
    """Convenience wrapper for one-off parsing."""
    return Parser(registry).parse(raw)


# --- field decoders --------------------------------------------------------


def _decode_array(
    arr: Array, raw: bytes, encoding: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(arr.count):
        elem_start = arr.offset + i * arr.record_length
        record: dict[str, Any] = {}
        for fld in arr.fields:
            slice_start = elem_start + fld.offset
            slice_end = slice_start + fld.length
            element_bytes = raw[slice_start:slice_end]
            record[fld.name] = _decode_field_slice(fld, element_bytes, encoding)
        out.append(record)
    return out


def _decode_field(fld: Field, raw: bytes, encoding: str) -> Any:
    slice_start = fld.offset
    slice_end = slice_start + fld.length
    return _decode_field_slice(fld, raw[slice_start:slice_end], encoding)


def _decode_field_slice(fld: Field, chunk: bytes, encoding: str) -> Any:
    if len(chunk) != fld.length:
        raise FieldDecodeError(
            fld.name, chunk, f"slice length {len(chunk)} != declared {fld.length}"
        )

    if fld.is_numeric_formatted:
        return _decode_numeric(fld, chunk)

    if fld.type == "Long":
        return _decode_long(fld, chunk)
    if fld.type == "String":
        return _decode_string(fld, chunk, encoding)
    if fld.type == "Float":
        return _decode_numeric(fld, chunk)
    raise FieldDecodeError(fld.name, chunk, f"unsupported field type {fld.type!r}")


def _decode_long(fld: Field, chunk: bytes) -> int:
    text = chunk.decode("ascii").strip()
    if text == "":
        return 0
    try:
        return int(text)
    except ValueError as exc:
        raise FieldDecodeError(fld.name, chunk, f"not an integer: {exc}") from exc


def _decode_string(fld: Field, chunk: bytes, encoding: str) -> str:
    try:
        text = chunk.decode(encoding)
    except UnicodeDecodeError as exc:
        raise FieldDecodeError(
            fld.name, chunk, f"cannot decode as {encoding}: {exc}"
        ) from exc
    return text.rstrip(" ")


def _decode_numeric(fld: Field, chunk: bytes) -> Decimal:
    """Decode a fixed-width numeric with either implicit or explicit
    decimal placement.

    When `length == int_digits + frac_digits + 1` the extra byte can
    be either:

    - **A literal decimal point** sitting between the integer and
      fractional halves (e.g. `000015.220000`), as observed in
      TCSMIH42101 samples. Selected when position `int_digits` is `.`.
    - **A leading sign byte** (`+`, `-`, `' '`, `'0'`) — kept for
      specs that actually carry signed values. Selected when the
      first byte is a sign character and the point is absent.

    When `length == int_digits + frac_digits`, all bytes are digits.
    """
    assert fld.int_digits is not None and fld.frac_digits is not None
    text = chunk.decode("ascii")

    sign = 1
    if fld.sign_bytes == 1:
        if len(text) > fld.int_digits and text[fld.int_digits] == ".":
            # Embedded decimal point. Strip it out and keep all digits.
            digits = text[: fld.int_digits] + text[fld.int_digits + 1 :]
        else:
            sign_char = text[0]
            if sign_char in (" ", "+", "0"):
                sign = 1
            elif sign_char == "-":
                sign = -1
            else:
                raise FieldDecodeError(
                    fld.name,
                    chunk,
                    f"unexpected sign byte {sign_char!r}"
                    f" (and byte at int_digits={fld.int_digits} is not '.')",
                )
            digits = text[1:]
    else:
        digits = text

    digits = digits.strip()
    if digits == "":
        return Decimal(0)
    if not digits.isdigit():
        raise FieldDecodeError(fld.name, chunk, f"non-digit content: {digits!r}")

    # Pad to full width (shouldn't be needed after the strip() above,
    # but guards against odd leading-space inputs).
    expected_digits = fld.int_digits + fld.frac_digits
    digits = digits.rjust(expected_digits, "0")

    int_part = digits[: fld.int_digits]
    frac_part = digits[fld.int_digits :]

    if fld.frac_digits == 0:
        value = Decimal(int_part)
    else:
        value = Decimal(f"{int_part}.{frac_part}")
    if sign == -1:
        value = -value
    return value
