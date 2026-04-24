"""SQLAlchemy ORM models.

Two tables:

- `raw_messages` — every payload the parser ingests, stored verbatim
  (BLOB), even when parsing fails. Keeps forensics possible.
- `parsed_messages` — one row per successfully parsed record, with
  the typed body serialised as JSON (Decimals → string to preserve
  precision; SQLite stores TEXT verbatim).
"""

from __future__ import annotations

import datetime as _dt
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class ParseStatus(StrEnum):
    PENDING = "pending"
    PARSED = "parsed"
    ERROR = "error"


class Base(DeclarativeBase):
    pass


class RawMessage(Base):
    __tablename__ = "raw_messages"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    received_at: Mapped[_dt.datetime] = mapped_column(
        sa.DateTime(timezone=False),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    payload: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    parse_status: Mapped[str] = mapped_column(
        sa.Text, nullable=False, default=ParseStatus.PENDING.value
    )
    error_detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    parsed: Mapped[ParsedMessageRow | None] = relationship(
        back_populates="raw",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        sa.Index("ix_raw_messages_parse_status", "parse_status"),
        sa.Index("ix_raw_messages_received_at", "received_at"),
    )


class ParsedMessageRow(Base):
    __tablename__ = "parsed_messages"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    raw_message_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("raw_messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # one parsed row per raw record
    )
    transaction_code: Mapped[str] = mapped_column(sa.Text, nullable=False)
    message_seq: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    transmit_date: Mapped[str] = mapped_column(sa.Text, nullable=False)  # YYYYMMDD
    emsg_complt_yn: Mapped[str] = mapped_column(sa.Text, nullable=False)
    body: Mapped[str] = mapped_column(sa.Text, nullable=False)

    raw: Mapped[RawMessage] = relationship(back_populates="parsed")

    __table_args__ = (
        sa.Index("ix_parsed_tr_code_date", "transaction_code", "transmit_date"),
        sa.Index("ix_parsed_transmit_date", "transmit_date"),
        sa.Index("ix_parsed_raw_message_id", "raw_message_id"),
    )
