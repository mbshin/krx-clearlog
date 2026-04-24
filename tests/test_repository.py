from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from krx_parser.db import Base, ParseStatus, Repository, create_engine_from_url
from krx_parser.db.models import ParsedMessageRow, RawMessage
from krx_parser.frame import parse_frame
from tests.builder import build_record
from tests.test_frame import build_header


@pytest.fixture()
def engine():
    eng = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture()
def repo(session, registry):
    return Repository(session, registry=registry)


def test_alembic_schema_matches_models(engine):
    inspector = sa.inspect(engine)
    assert "raw_messages" in inspector.get_table_names()
    assert "parsed_messages" in inspector.get_table_names()
    idx_names = {i["name"] for i in inspector.get_indexes("parsed_messages")}
    assert {"ix_parsed_tr_code_date", "ix_parsed_transmit_date"} <= idx_names


def test_ingest_round_trips_flat_message(repo, registry):
    schema = registry.get("TCSMIH42201")
    payload = build_record(schema, fields={
        "MESSAGE_SEQUENCE_NUMBER": 7,
        "TRANSACTION_CODE": "TCSMIH42201",
        "TRANSMIT_DATE": "20260424",
        "EMSG_COMPLT_YN": "Y",
        "MEMBER_NUMBER": "M0042",
        "NON_CLEARING_MEMBER_NUMBER": "NC042",
        "TRUST_PRINCIPAL_INTEGRATION_TYPE_CODE": "10",
        "TRADING_MARGIN_REQUIRED_VALUE": Decimal("123456.789"),
        "CASHABLE_ASSET_PAY_REQUIRED_VALUE": Decimal("-200.500"),
    })
    stored = repo.ingest(payload, source="pytest")
    assert stored.transaction_code == "TCSMIH42201"
    assert stored.message_sequence_number == 7
    assert stored.transmit_date == "20260424"
    assert stored.fields["TRADING_MARGIN_REQUIRED_VALUE"] == Decimal("123456.789")

    fetched = repo.get(stored.parsed_id)
    assert fetched is not None
    assert fetched.fields["MEMBER_NUMBER"] == "M0042"
    assert fetched.fields["CASHABLE_ASSET_PAY_REQUIRED_VALUE"] == Decimal("-200.500")
    assert fetched.payload == payload


def test_ingest_round_trips_array_message(repo, registry):
    schema = registry.get("TCSMIH43501")
    issues = [
        {
            "TRUST_PRINCIPAL_INTEGRATION_TYPE_CODE": "10",
            "MARKET_IDENTIFICATION": "STK",
            "SECURITIES_GROUP_IDENTIFICATION": "SG",
            "ISSUE_CODE": f"KR{i:010d}",
            "ASK_TRADING_VOLUME": i,
            "BID_TRADING_VOLUME": 2 * i,
            "TRADING_VOLUME_WEIGHTED_AVERAGE_PRICE": 10_000 + i,
        }
        for i in range(20)
    ]
    payload = build_record(schema, fields={
        "MESSAGE_SEQUENCE_NUMBER": 1,
        "TRANSACTION_CODE": "TCSMIH43501",
        "TRANSMIT_DATE": "20260424",
        "EMSG_COMPLT_YN": "Y",
        "MEMBER_NUMBER": "M0001",
    }, arrays={"issues": issues})
    stored = repo.ingest(payload, source="pytest")
    loaded = repo.get(stored.parsed_id)
    assert loaded is not None
    assert len(loaded.arrays["issues"]) == 20
    assert loaded.arrays["issues"][5]["ISSUE_CODE"] == "KR0000000005"


def test_ingest_records_parse_error(repo, session):
    junk = b"X" * 1200
    # The first 11 bytes of junk are "XXXXXXXXXXX" then "XXXXXXXXXXX" as TR
    # code — not in the registry. We expect an error row, no parsed row.
    result = repo.ingest(junk, source="pytest")
    assert isinstance(result, RawMessage)
    assert result.parse_status == ParseStatus.ERROR.value
    assert "UnknownMessageType" in (result.error_detail or "")
    # No parsed row linked.
    assert session.scalar(
        sa.select(sa.func.count(ParsedMessageRow.id))
    ) == 0


def test_search_filters(repo, registry):
    schema = registry.get("TCSMIH42201")
    for i, (date, member) in enumerate(
        [
            ("20260420", "M001"),
            ("20260421", "M001"),
            ("20260423", "M002"),
            ("20260424", "M002"),
        ]
    ):
        payload = build_record(schema, fields={
            "MESSAGE_SEQUENCE_NUMBER": i + 1,
            "TRANSACTION_CODE": "TCSMIH42201",
            "TRANSMIT_DATE": date,
            "EMSG_COMPLT_YN": "Y",
            "MEMBER_NUMBER": member,
        })
        repo.ingest(payload, source="pytest")

    assert len(repo.search(transaction_code="TCSMIH42201")) == 4
    assert len(repo.search(member_number="M001")) == 2
    assert len(repo.search(member_number="M002")) == 2
    assert (
        len(repo.search(transmit_date_from="20260422", transmit_date_to="20260423"))
        == 1
    )
    assert len(repo.search(transmit_date_from="20260423")) == 2


def test_ingest_frame_plaintext_parses(repo, registry):
    schema = registry.get("TCSMIH42201")
    data = build_record(schema, fields={
        "MESSAGE_SEQUENCE_NUMBER": 1,
        "TRANSACTION_CODE": "TCSMIH42201",
        "TRANSMIT_DATE": "20260424",
        "EMSG_COMPLT_YN": "Y",
        "MEMBER_NUMBER": "M0001",
    })
    raw = build_header(tr_code="TCSMIH42201", data_length=len(data), seq=1) + data
    frame = parse_frame(raw)

    stored = repo.ingest_frame(frame, source="pytest")
    from krx_parser.db.repository import StoredMessage

    assert isinstance(stored, StoredMessage)
    assert stored.transaction_code == "TCSMIH42201"
    assert stored.fields["MEMBER_NUMBER"] == "M0001"


def test_ingest_frame_encrypted_parks_as_error(repo, session):
    data = b"\x00" * 1200
    raw = build_header(tr_code="TCSMIH42201", data_length=1200, encrypted="Y") + data
    frame = parse_frame(raw)

    result = repo.ingest_frame(frame, source="pytest")
    assert isinstance(result, RawMessage)
    assert result.parse_status == ParseStatus.ERROR.value
    assert "encrypted" in (result.error_detail or "")
    # Full envelope + DATA preserved for forensic decryption later.
    assert result.payload == frame.raw
    assert session.scalar(
        sa.select(sa.func.count(ParsedMessageRow.id))
    ) == 0


def test_count_by_transaction_code(repo, registry):
    for tr in ("TCSMIH42201", "TCSMIH42201", "TCSMIH43201"):
        schema = registry.get(tr)
        payload = build_record(schema, fields={
            "TRANSACTION_CODE": tr,
            "TRANSMIT_DATE": "20260424",
            "EMSG_COMPLT_YN": "Y",
            "MESSAGE_SEQUENCE_NUMBER": 1,
        })
        repo.ingest(payload, source="pytest")
    assert repo.count_by_transaction_code() == {
        "TCSMIH42201": 2,
        "TCSMIH43201": 1,
    }
