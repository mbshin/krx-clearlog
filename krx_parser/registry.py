"""Schema registry.

Loads all `*.yaml` files under a directory (default:
`krx_parser/schemas/`) and exposes a `SchemaRegistry` keyed on
`TRANSACTION_CODE`. Also provides a small set of file-level CRUD
helpers for the Streamlit schema editor.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from krx_parser.exceptions import SchemaValidationError, UnknownMessageType
from krx_parser.schema import Schema, build_schema

SCHEMA_DIR = Path(__file__).parent / "schemas"


NEW_SCHEMA_TEMPLATE = """\
transaction_code: TCSMIH00000
description: (describe the message here)
market: equity
encoding: euc-kr
record_length: 1200

layout:
  - kind: field
    name: MESSAGE_SEQUENCE_NUMBER
    kor_name: 메세지일련번호
    kor_description: 메시지 일련번호
    type: Long
    length: 11
  - kind: field
    name: TRANSACTION_CODE
    kor_name: 트랜잭션코드
    kor_description: 거래 코드 (TCSMIH00000)
    type: String
    length: 11
  - kind: field
    name: TRANSMIT_DATE
    kor_name: 전송일자
    kor_description: 전송일자 YYYYMMDD
    type: String
    length: 8
  - kind: field
    name: EMSG_COMPLT_YN
    kor_name: 전문완료여부
    kor_description: Y=전문완료, N=전송중
    type: String
    length: 1
  - kind: field
    name: FILLER_VALUE
    kor_name: 필러값
    kor_description: 예비 영역
    type: String
    length: 1169
"""


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
    return parse_schema_yaml(path.read_text(encoding="utf-8"), source=path.name)


# --- file-level CRUD ----------------------------------------------------


def parse_schema_yaml(text: str, *, source: str = "<memory>") -> Schema:
    """Parse + validate a YAML blob. Raises `SchemaValidationError` on
    any problem. Always safe to call on untrusted input."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SchemaValidationError(f"{source}: YAML error: {exc}") from exc
    if not isinstance(raw, dict):
        raise SchemaValidationError(
            f"{source}: top-level YAML must be a mapping, got {type(raw).__name__}"
        )
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
            f"{source}: missing required key {exc.args[0]!r}"
        ) from exc


def list_schema_files(schema_dir: Path = SCHEMA_DIR) -> list[Path]:
    return sorted(schema_dir.glob("*.yaml"))


def read_schema_text(transaction_code: str, schema_dir: Path = SCHEMA_DIR) -> str:
    """Return the raw YAML text for a TR code, or empty string if not on disk."""
    path = schema_dir / f"{transaction_code}.yaml"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_schema_text(
    text: str,
    *,
    schema_dir: Path = SCHEMA_DIR,
    expected_transaction_code: str | None = None,
) -> Schema:
    """Validate the YAML, ensure it's self-consistent, then atomically
    write to `<schema_dir>/<transaction_code>.yaml`. Returns the
    validated `Schema`. Raises `SchemaValidationError` otherwise.

    If `expected_transaction_code` is given, the YAML's
    `transaction_code` must match — prevents accidentally renaming a
    file while editing it.
    """
    schema = parse_schema_yaml(text)
    if (
        expected_transaction_code is not None
        and schema.transaction_code != expected_transaction_code
    ):
        raise SchemaValidationError(
            f"transaction_code mismatch: file is for {expected_transaction_code!r}"
            f" but YAML declares {schema.transaction_code!r}"
        )

    schema_dir.mkdir(parents=True, exist_ok=True)
    target = schema_dir / f"{schema.transaction_code}.yaml"
    tmp = target.with_suffix(".yaml.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
    return schema


def delete_schema_file(
    transaction_code: str, schema_dir: Path = SCHEMA_DIR
) -> bool:
    """Remove the YAML file for a TR code. Returns True if a file was
    deleted, False if it wasn't present."""
    path = schema_dir / f"{transaction_code}.yaml"
    if not path.exists():
        return False
    path.unlink()
    return True
