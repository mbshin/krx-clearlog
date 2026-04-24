"""Byte-encoder helpers for tests.

Builds fixed-width record bytes from Python values, matching the parser
schema. Lets the round-trip tests assert `parse(build(values)) == values`
without hand-crafting raw bytes.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from krx_parser.schema import Array, Field, Schema


def build_record(
    schema: Schema,
    fields: dict[str, Any] | None = None,
    arrays: dict[str, list[dict[str, Any]]] | None = None,
) -> bytes:
    fields = fields or {}
    arrays = arrays or {}
    out = bytearray()
    for item in schema.layout:
        if isinstance(item, Field):
            out += encode_field(item, fields.get(item.name), schema.encoding)
        elif isinstance(item, Array):
            records = arrays.get(item.name, [])
            out += encode_array(item, records, schema.encoding)
    if len(out) != schema.record_length:
        raise AssertionError(
            f"built {len(out)} bytes but schema {schema.transaction_code}"
            f" declares record_length {schema.record_length}"
        )
    return bytes(out)


def encode_array(
    arr: Array, records: list[dict[str, Any]], encoding: str
) -> bytes:
    out = bytearray()
    for i in range(arr.count):
        record = records[i] if i < len(records) else {}
        for fld in arr.fields:
            out += encode_field(fld, record.get(fld.name), encoding)
    return bytes(out)


def encode_field(fld: Field, value: Any, encoding: str) -> bytes:
    if fld.is_numeric_formatted:
        return encode_numeric(fld, Decimal(0) if value is None else Decimal(value))
    if fld.type == "Long":
        return encode_long(fld, 0 if value is None else int(value))
    if fld.type == "String":
        return encode_string(fld, "" if value is None else str(value), encoding)
    if fld.type == "Float":
        return encode_numeric(fld, Decimal(0) if value is None else Decimal(value))
    raise AssertionError(f"unsupported field type {fld.type!r}")


def encode_long(fld: Field, value: int) -> bytes:
    if value < 0:
        raise ValueError(f"{fld.name}: Long fields are unsigned-ASCII; got {value}")
    text = str(value).rjust(fld.length, "0")
    if len(text) > fld.length:
        raise ValueError(f"{fld.name}: value {value} exceeds {fld.length} digits")
    return text.encode("ascii")


def encode_string(fld: Field, value: str, encoding: str) -> bytes:
    encoded = value.encode(encoding)
    if len(encoded) > fld.length:
        raise ValueError(
            f"{fld.name}: encoded length {len(encoded)} > declared {fld.length}"
        )
    return encoded.ljust(fld.length, b" ")


def encode_numeric(fld: Field, value: Decimal) -> bytes:
    assert fld.int_digits is not None and fld.frac_digits is not None
    sign_bytes = fld.sign_bytes
    sign = " "
    magnitude = value
    if value < 0:
        if sign_bytes == 0:
            raise ValueError(
                f"{fld.name}: negative value requires sign byte but field has none"
            )
        sign = "-"
        magnitude = -value

    quantized = magnitude.scaleb(fld.frac_digits)
    int_value = int(quantized)
    width = fld.int_digits + fld.frac_digits
    digits = str(int_value).rjust(width, "0")
    if len(digits) > width:
        raise ValueError(
            f"{fld.name}: value {value} needs {len(digits)} digits, budget is {width}"
        )
    if sign_bytes == 1:
        return (sign + digits).encode("ascii")
    return digits.encode("ascii")
