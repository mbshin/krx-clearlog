"""Repository layer over `raw_messages` + `parsed_messages`.

Thin helpers for the UI: accept a raw payload, parse it, persist both
rows in a single transaction; query by the filters the Lookup page
exposes.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from krx_parser.db.models import ParsedMessageRow, ParseStatus, RawMessage
from krx_parser.db.serialize import body_from_json, body_to_json
from krx_parser.exceptions import KrxParserError
from krx_parser.parser import ParsedMessage, Parser
from krx_parser.registry import SchemaRegistry


@dataclass(frozen=True)
class StoredMessage:
    """Read-side projection of a persisted parsed message."""

    raw_id: int
    parsed_id: int
    transaction_code: str
    message_sequence_number: int
    transmit_date: str
    emsg_complt_yn: str
    received_at: _dt.datetime
    source: str
    fields: dict[str, Any]
    arrays: dict[str, list[dict[str, Any]]]
    payload: bytes


class Repository:
    def __init__(
        self,
        session: Session,
        parser: Parser | None = None,
        registry: SchemaRegistry | None = None,
    ) -> None:
        self.session = session
        self._registry = registry or (parser.registry if parser else None)
        self._parser = parser or (Parser(registry) if registry is not None else Parser())
        if self._registry is None:
            self._registry = self._parser.registry

    # --- writes -------------------------------------------------------

    def ingest(self, payload: bytes, *, source: str) -> StoredMessage | RawMessage:
        """Parse + persist. On parse failure, the raw row is saved with
        `parse_status='error'` and no parsed row; the caller gets back
        the `RawMessage` so it can surface the error."""
        raw = RawMessage(
            source=source, payload=payload, parse_status=ParseStatus.PENDING.value
        )
        self.session.add(raw)
        self.session.flush()

        try:
            parsed = self._parser.parse(payload)
        except KrxParserError as exc:
            raw.parse_status = ParseStatus.ERROR.value
            raw.error_detail = f"{type(exc).__name__}: {exc}"
            self.session.flush()
            return raw

        row = _to_row(raw.id, parsed)
        self.session.add(row)
        raw.parse_status = ParseStatus.PARSED.value
        self.session.flush()

        return StoredMessage(
            raw_id=raw.id,
            parsed_id=row.id,
            transaction_code=row.transaction_code,
            message_sequence_number=row.message_seq,
            transmit_date=row.transmit_date,
            emsg_complt_yn=row.emsg_complt_yn,
            received_at=raw.received_at,
            source=raw.source,
            fields=parsed.fields,
            arrays=parsed.arrays,
            payload=payload,
        )

    def ingest_many(self, payloads: Iterable[bytes], *, source: str) -> list[object]:
        return [self.ingest(p, source=source) for p in payloads]

    # --- reads --------------------------------------------------------

    def get(self, parsed_id: int) -> StoredMessage | None:
        row = self.session.get(ParsedMessageRow, parsed_id)
        if row is None:
            return None
        return self._hydrate(row)

    def search(
        self,
        *,
        transaction_code: str | None = None,
        transmit_date_from: str | None = None,
        transmit_date_to: str | None = None,
        member_number: str | None = None,
        underlying_asset_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StoredMessage]:
        stmt = (
            sa.select(ParsedMessageRow)
            .join(RawMessage, ParsedMessageRow.raw_message_id == RawMessage.id)
            .order_by(ParsedMessageRow.id.desc())
        )
        if transaction_code:
            stmt = stmt.where(ParsedMessageRow.transaction_code == transaction_code)
        if transmit_date_from:
            stmt = stmt.where(ParsedMessageRow.transmit_date >= transmit_date_from)
        if transmit_date_to:
            stmt = stmt.where(ParsedMessageRow.transmit_date <= transmit_date_to)
        if member_number:
            stmt = stmt.where(
                sa.func.json_extract(ParsedMessageRow.body, "$.fields.MEMBER_NUMBER")
                == member_number
            )
        if underlying_asset_code:
            stmt = stmt.where(
                sa.func.json_extract(
                    ParsedMessageRow.body, "$.fields.UNDERLYING_ASSET_CODE"
                )
                == underlying_asset_code
            )
        stmt = stmt.limit(limit).offset(offset)

        return [self._hydrate(row) for row in self.session.scalars(stmt).all()]

    def count_by_transaction_code(self) -> dict[str, int]:
        stmt = sa.select(
            ParsedMessageRow.transaction_code,
            sa.func.count(ParsedMessageRow.id),
        ).group_by(ParsedMessageRow.transaction_code)
        return {tr: n for tr, n in self.session.execute(stmt).all()}

    # --- internals ----------------------------------------------------

    def _hydrate(self, row: ParsedMessageRow) -> StoredMessage:
        schema = (
            self._registry.get(row.transaction_code)
            if row.transaction_code in self._registry
            else None
        )
        fields, arrays = body_from_json(row.body, schema)
        return StoredMessage(
            raw_id=row.raw_message_id,
            parsed_id=row.id,
            transaction_code=row.transaction_code,
            message_sequence_number=row.message_seq,
            transmit_date=row.transmit_date,
            emsg_complt_yn=row.emsg_complt_yn,
            received_at=row.raw.received_at,
            source=row.raw.source,
            fields=fields,
            arrays=arrays,
            payload=row.raw.payload,
        )


def _to_row(raw_message_id: int, parsed: ParsedMessage) -> ParsedMessageRow:
    return ParsedMessageRow(
        raw_message_id=raw_message_id,
        transaction_code=parsed.transaction_code,
        message_seq=parsed.message_sequence_number,
        transmit_date=parsed.transmit_date,
        emsg_complt_yn=parsed.emsg_complt_yn,
        body=body_to_json(parsed.fields, parsed.arrays),
    )
