"""initial schema: raw_messages + parsed_messages

Revision ID: 0001
Revises:
Create Date: 2026-04-24

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "raw_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("payload", sa.LargeBinary, nullable=False),
        sa.Column(
            "parse_status", sa.Text, nullable=False, server_default="pending"
        ),
        sa.Column("error_detail", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_raw_messages_parse_status", "raw_messages", ["parse_status"]
    )
    op.create_index(
        "ix_raw_messages_received_at", "raw_messages", ["received_at"]
    )

    op.create_table(
        "parsed_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "raw_message_id",
            sa.Integer,
            sa.ForeignKey("raw_messages.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("transaction_code", sa.Text, nullable=False),
        sa.Column("message_seq", sa.Integer, nullable=False),
        sa.Column("transmit_date", sa.Text, nullable=False),
        sa.Column("emsg_complt_yn", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
    )
    op.create_index(
        "ix_parsed_tr_code_date",
        "parsed_messages",
        ["transaction_code", "transmit_date"],
    )
    op.create_index(
        "ix_parsed_transmit_date", "parsed_messages", ["transmit_date"]
    )
    op.create_index(
        "ix_parsed_raw_message_id", "parsed_messages", ["raw_message_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_parsed_raw_message_id", table_name="parsed_messages")
    op.drop_index("ix_parsed_transmit_date", table_name="parsed_messages")
    op.drop_index("ix_parsed_tr_code_date", table_name="parsed_messages")
    op.drop_table("parsed_messages")
    op.drop_index("ix_raw_messages_received_at", table_name="raw_messages")
    op.drop_index("ix_raw_messages_parse_status", table_name="raw_messages")
    op.drop_table("raw_messages")
