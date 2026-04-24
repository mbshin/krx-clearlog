"""Shared helpers for the Streamlit app.

Keep anything heavier than plain widget plumbing out of the page
modules — Streamlit re-imports pages on every interaction.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import streamlit as st
from sqlalchemy.orm import Session

from krx_parser.db import Base, Repository, create_engine_from_url, get_sessionmaker
from krx_parser.frame import MARKER, KmapFrame, iter_frames
from krx_parser.parser import Parser
from krx_parser.registry import SchemaRegistry, load_default_registry
from krx_parser.schema import Array, Field, Schema
from krx_parser.settings import get_settings


@st.cache_resource
def get_registry() -> SchemaRegistry:
    return load_default_registry()


@st.cache_resource
def get_parser() -> Parser:
    return Parser(get_registry())


@st.cache_resource
def get_engine_cached():
    settings = get_settings()
    engine = create_engine_from_url(settings.database_url)
    # For SQLite, create tables on first run so the app works without
    # requiring the user to run `alembic upgrade head` first. Alembic is
    # still the source of truth for production migrations.
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def session_scope() -> Iterator[Session]:
    session_factory = get_sessionmaker(get_engine_cached())
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def repo_scope() -> Iterator[Repository]:
    with session_scope() as session:
        yield Repository(session, registry=get_registry())


# --- record slicing ------------------------------------------------------


def iter_records(payload: bytes, parser: Parser | None = None) -> Iterator[bytes]:
    """Yield fixed-width record bytes from a concatenated stream.

    Uses the TR code at offset 11 to look up each record's length, so
    mixed TR codes in one stream are handled. Trailing bytes shorter
    than a full record are dropped.
    """
    parser = parser or get_parser()
    i = 0
    n = len(payload)
    while i + 22 <= n:
        try:
            tr = parser.peek_transaction_code(payload[i : i + 22])
        except Exception:
            break
        if tr not in parser.registry:
            break
        rec_len = parser.record_length(tr)
        if i + rec_len > n:
            break
        yield payload[i : i + rec_len]
        i += rec_len


def looks_like_kmap_stream(payload: bytes) -> bool:
    """Heuristic: input contains at least one KMAPv2 frame marker."""
    return MARKER in payload


def extract(
    payload: bytes,
) -> tuple[list[KmapFrame], list[bytes]]:
    """Return (frames, loose_records). Exactly one of the two will be non-empty.

    If the input looks like a KMAPv2 stream (e.g. an app log with
    embedded frames), we scan for frames and ignore bytes between
    them. Otherwise we treat the input as already-extracted records
    and slice them by TR-code-derived lengths.
    """
    if looks_like_kmap_stream(payload):
        return list(iter_frames(payload)), []
    return [], list(iter_records(payload))


def sanitize_paste(text: str) -> bytes:
    """Strip line terminators and treat input as EUC-KR bytes.

    Streamlit text inputs come in as Python str — for a raw-bytes flow
    the user uploads a file instead. The paste path is best-effort for
    already-extracted records.
    """
    return text.replace("\r\n", "").replace("\n", "").encode("euc-kr", errors="replace")


# --- label / dataframe helpers ------------------------------------------


def korean_labels(schema: Schema) -> dict[str, str]:
    """Flat-field `EN → KR` map (array fields excluded)."""
    out: dict[str, str] = {}
    for item in schema.layout:
        if isinstance(item, Field):
            out[item.name] = item.kor_name
    return out


def iter_flat_fields(schema: Schema) -> Iterator[Field]:
    for item in schema.layout:
        if isinstance(item, Field):
            yield item


def iter_arrays(schema: Schema) -> Iterator[Array]:
    for item in schema.layout:
        if isinstance(item, Array):
            yield item


def format_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
