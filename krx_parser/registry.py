"""Schema registry.

Loads all `*.yaml` files under a directory (default:
`krx_parser/schemas/`) and exposes a `SchemaRegistry` keyed on
`TRANSACTION_CODE`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from krx_parser.exceptions import SchemaValidationError, UnknownMessageType
from krx_parser.schema import Schema, build_schema

SCHEMA_DIR = Path(__file__).parent / "schemas"


class SchemaRegistry:
    def __init__(self, schemas: dict[str, Schema]) -> None:
        self._schemas = schemas

    def get(self, transaction_code: str) -> Schema:
        try:
            return self._schemas[transaction_code]
        except KeyError:
            raise UnknownMessageType(transaction_code) from None

    def __contains__(self, transaction_code: str) -> bool:
        return transaction_code in self._schemas

    def codes(self) -> list[str]:
        return sorted(self._schemas.keys())

    def __iter__(self):
        return iter(self._schemas.values())

    def __len__(self) -> int:
        return len(self._schemas)


def load_registry(schema_dir: Path) -> SchemaRegistry:
    schemas: dict[str, Schema] = {}
    for path in sorted(schema_dir.glob("*.yaml")):
        schema = _load_schema_file(path)
        if schema.transaction_code in schemas:
            raise SchemaValidationError(
                f"duplicate TRANSACTION_CODE {schema.transaction_code!r} in {path}"
            )
        schemas[schema.transaction_code] = schema
    return SchemaRegistry(schemas)


def load_default_registry() -> SchemaRegistry:
    return load_registry(SCHEMA_DIR)


def _load_schema_file(path: Path) -> Schema:
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    try:
        return build_schema(
            transaction_code=raw["transaction_code"],
            description=raw["description"],
            market=raw["market"],
            encoding=raw["encoding"],
            record_length=int(raw["record_length"]),
            raw_layout=raw["layout"],
        )
    except KeyError as exc:
        raise SchemaValidationError(
            f"{path.name}: missing required key {exc.args[0]!r}"
        ) from exc
