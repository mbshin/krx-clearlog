"""Schema types for KRX fixed-width messages.

A schema describes a single TR code's byte layout as an ordered sequence
of `LayoutItem`s — either a `Field` or an `Array` of per-record fields.
Offsets are computed at load time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from krx_parser.exceptions import SchemaValidationError

FieldType = Literal["Long", "String", "Float"]


@dataclass(frozen=True)
class Field:
    name: str
    kor_name: str
    kor_description: str
    type: FieldType
    length: int
    offset: int  # byte offset within the *containing* layout (message or array element)
    int_digits: int | None = None
    frac_digits: int | None = None

    @property
    def is_numeric_formatted(self) -> bool:
        """Field carries implied decimal placement (int_digits/frac_digits)."""
        return self.int_digits is not None and self.frac_digits is not None

    @property
    def sign_bytes(self) -> int:
        """Extra leading bytes beyond int_digits+frac_digits (sign indicator)."""
        if not self.is_numeric_formatted:
            return 0
        assert self.int_digits is not None and self.frac_digits is not None
        extra = self.length - self.int_digits - self.frac_digits
        if extra not in (0, 1):
            raise SchemaValidationError(
                f"field {self.name!r}: length {self.length} - int_digits {self.int_digits}"
                f" - frac_digits {self.frac_digits} = {extra}; expected 0 or 1 (sign byte)"
            )
        return extra


@dataclass(frozen=True)
class Array:
    name: str
    count: int
    offset: int                 # start of array within the message
    record_length: int          # bytes per element
    fields: tuple[Field, ...]   # per-element fields (offsets are within an element)

    @property
    def total_length(self) -> int:
        return self.count * self.record_length


LayoutItem = Field | Array


@dataclass(frozen=True)
class Schema:
    transaction_code: str
    description: str
    market: str              # "derivatives" | "equity"
    encoding: str            # "euc-kr"
    record_length: int
    layout: tuple[LayoutItem, ...]

    def item_by_name(self, name: str) -> LayoutItem | None:
        for item in self.layout:
            if item.name == name:
                return item
        return None

    def field_by_name(self, name: str) -> Field | None:
        item = self.item_by_name(name)
        return item if isinstance(item, Field) else None


def build_schema(
    *,
    transaction_code: str,
    description: str,
    market: str,
    encoding: str,
    record_length: int,
    raw_layout: list[dict],
) -> Schema:
    """Construct a `Schema` from a raw YAML-decoded layout list.

    Computes byte offsets in order and validates that the sum of item
    lengths equals the declared `record_length`. Also validates each
    Float/numeric field's int_digits/frac_digits vs length.
    """
    layout: list[LayoutItem] = []
    offset = 0
    for raw in raw_layout:
        kind = raw.get("kind", "field")
        if kind == "field":
            fld = _build_field(raw, offset=offset)
            _ = fld.sign_bytes  # triggers validation
            layout.append(fld)
            offset += fld.length
        elif kind == "array":
            arr = _build_array(raw, offset=offset)
            layout.append(arr)
            offset += arr.total_length
        else:
            raise SchemaValidationError(f"unknown layout kind: {kind!r}")

    if offset != record_length:
        raise SchemaValidationError(
            f"{transaction_code}: layout sum {offset} != declared record_length {record_length}"
        )

    return Schema(
        transaction_code=transaction_code,
        description=description,
        market=market,
        encoding=encoding,
        record_length=record_length,
        layout=tuple(layout),
    )


def _build_field(raw: dict, *, offset: int) -> Field:
    try:
        return Field(
            name=raw["name"],
            kor_name=raw["kor_name"],
            kor_description=raw.get("kor_description", ""),
            type=raw["type"],
            length=int(raw["length"]),
            offset=offset,
            int_digits=raw.get("int_digits"),
            frac_digits=raw.get("frac_digits"),
        )
    except KeyError as exc:
        raise SchemaValidationError(f"field missing required key: {exc.args[0]!r}") from exc


def _build_array(raw: dict, *, offset: int) -> Array:
    try:
        name = raw["name"]
        count = int(raw["count"])
        raw_fields = raw["fields"]
    except KeyError as exc:
        raise SchemaValidationError(f"array missing required key: {exc.args[0]!r}") from exc

    member_fields: list[Field] = []
    elem_offset = 0
    for rf in raw_fields:
        fld = _build_field(rf, offset=elem_offset)
        _ = fld.sign_bytes
        member_fields.append(fld)
        elem_offset += fld.length

    return Array(
        name=name,
        count=count,
        offset=offset,
        record_length=elem_offset,
        fields=tuple(member_fields),
    )
