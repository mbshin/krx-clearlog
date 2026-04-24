"""JSON (de)serialisation for ParsedMessage bodies.

Decimals are written as strings so that SQLite TEXT storage preserves
exact precision — binary Float would lose digits on round-trip. On
read, Decimal-typed fields are coerced back using the schema; unknown
fields fall through as strings (safe no-op for UI display).
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from krx_parser.schema import Array, Field, Schema


def body_to_json(
    fields: dict[str, Any],
    arrays: dict[str, list[dict[str, Any]]],
) -> str:
    return json.dumps(
        {"fields": fields, "arrays": arrays},
        default=_default,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def body_from_json(raw: str, schema: Schema | None = None) -> tuple[
    dict[str, Any], dict[str, list[dict[str, Any]]]
]:
    doc = json.loads(raw)
    fields: dict[str, Any] = doc.get("fields", {})
    arrays: dict[str, list[dict[str, Any]]] = doc.get("arrays", {})
    if schema is not None:
        _coerce(fields, arrays, schema)
    return fields, arrays


def _default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"cannot serialise {type(obj).__name__}")


def _coerce(
    fields: dict[str, Any],
    arrays: dict[str, list[dict[str, Any]]],
    schema: Schema,
) -> None:
    for item in schema.layout:
        if isinstance(item, Field) and item.is_numeric_formatted:
            name = item.name
            if name in fields and isinstance(fields[name], str):
                fields[name] = Decimal(fields[name])
        elif isinstance(item, Array):
            records = arrays.get(item.name, [])
            for rec in records:
                for fld in item.fields:
                    if (
                        fld.is_numeric_formatted
                        and fld.name in rec
                        and isinstance(rec[fld.name], str)
                    ):
                        rec[fld.name] = Decimal(rec[fld.name])
