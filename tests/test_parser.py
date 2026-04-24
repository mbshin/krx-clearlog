from decimal import Decimal

import pytest

from krx_parser import Parser, UnknownMessageType, parse
from krx_parser.codes import (
    EmsgCompltYn,
    OvresShortsTypeCode,
    TransactionCode,
    TrustPrincipalIntegrationTypeCode,
)
from krx_parser.exceptions import FieldDecodeError, SchemaValidationError
from tests.builder import build_record


def test_registry_loads_all_11_codes(registry):
    expected = {tc.value for tc in TransactionCode}
    assert set(registry.codes()) == expected
    assert len(registry) == 11


@pytest.mark.parametrize("tr_code", [tc.value for tc in TransactionCode])
def test_every_schema_has_1200_byte_records(registry, tr_code):
    assert registry.get(tr_code).record_length == 1200


@pytest.mark.parametrize("tr_code", [tc.value for tc in TransactionCode])
def test_default_record_round_trips(registry, tr_code):
    """An all-defaults record should build and parse without losing the header."""
    schema = registry.get(tr_code)
    raw = build_record(schema, fields={
        "TRANSACTION_CODE": tr_code,
        "TRANSMIT_DATE": "20260424",
        "EMSG_COMPLT_YN": EmsgCompltYn.COMPLETE.value,
        "MESSAGE_SEQUENCE_NUMBER": 1,
    })
    assert len(raw) == 1200

    parsed = parse(raw, registry)
    assert parsed.transaction_code == tr_code
    assert parsed.message_sequence_number == 1
    assert parsed.transmit_date == "20260424"
    assert parsed.emsg_complt_yn == "Y"


def test_flat_message_round_trip(registry):
    """TCSMIH42201 — all flat fields, including two Float(18.3) with sign byte."""
    schema = registry.get("TCSMIH42201")
    raw = build_record(schema, fields={
        "MESSAGE_SEQUENCE_NUMBER": 42,
        "TRANSACTION_CODE": "TCSMIH42201",
        "TRANSMIT_DATE": "20260424",
        "EMSG_COMPLT_YN": "Y",
        "MEMBER_NUMBER": "M0001",
        "NON_CLEARING_MEMBER_NUMBER": "NC001",
        "TRUST_PRINCIPAL_INTEGRATION_TYPE_CODE": TrustPrincipalIntegrationTypeCode.TRUST.value,
        "TRADING_MARGIN_REQUIRED_VALUE": Decimal("123456.789"),
        "CASHABLE_ASSET_PAY_REQUIRED_VALUE": Decimal("0.500"),
    })

    parsed = parse(raw, registry)
    assert parsed.fields["MEMBER_NUMBER"] == "M0001"
    assert parsed.fields["NON_CLEARING_MEMBER_NUMBER"] == "NC001"
    assert parsed.fields["TRUST_PRINCIPAL_INTEGRATION_TYPE_CODE"] == "10"
    assert parsed.fields["TRADING_MARGIN_REQUIRED_VALUE"] == Decimal("123456.789")
    assert parsed.fields["CASHABLE_ASSET_PAY_REQUIRED_VALUE"] == Decimal("0.500")


def test_repeating_group_round_trip(registry):
    """TCSMIH42101 — one array of 16 records, each with 5 fields."""
    schema = registry.get("TCSMIH42101")
    issues = [
        {
            "MARKET_IDENTIFICATION": "STK",
            "SECURITIES_GROUP_IDENTIFICATION": "SG",
            "ISSUE_CODE": f"KR{i:010d}",
            "ISU_KOR_ABBRV": f"종목{i:02d}",
            "TRD_MRGN_RT": Decimal(f"{i}.500000"),
        }
        for i in range(16)
    ]
    raw = build_record(schema, fields={
        "MESSAGE_SEQUENCE_NUMBER": 1,
        "TRANSACTION_CODE": "TCSMIH42101",
        "TRANSMIT_DATE": "20260424",
        "EMSG_COMPLT_YN": "Y",
    }, arrays={"issues": issues})

    parsed = parse(raw, registry)
    assert len(parsed.arrays["issues"]) == 16
    for i, record in enumerate(parsed.arrays["issues"]):
        assert record["MARKET_IDENTIFICATION"] == "STK"
        assert record["SECURITIES_GROUP_IDENTIFICATION"] == "SG"
        assert record["ISSUE_CODE"] == f"KR{i:010d}"
        assert record["ISU_KOR_ABBRV"] == f"종목{i:02d}"
        assert record["TRD_MRGN_RT"] == Decimal(f"{i}.500000")


def test_array_with_mixed_long_fields(registry):
    """TCSMIH43501 — array of 20 elements, three Long fields per element."""
    schema = registry.get("TCSMIH43501")
    issues = [
        {
            "TRUST_PRINCIPAL_INTEGRATION_TYPE_CODE": "10",
            "MARKET_IDENTIFICATION": "STK",
            "SECURITIES_GROUP_IDENTIFICATION": "SG",
            "ISSUE_CODE": f"KR{i:010d}",
            "ASK_TRADING_VOLUME": 100 * i,
            "BID_TRADING_VOLUME": 200 * i,
            "TRADING_VOLUME_WEIGHTED_AVERAGE_PRICE": 10_000 + i,
        }
        for i in range(20)
    ]
    raw = build_record(schema, fields={
        "MESSAGE_SEQUENCE_NUMBER": 7,
        "TRANSACTION_CODE": "TCSMIH43501",
        "TRANSMIT_DATE": "20260424",
        "EMSG_COMPLT_YN": "Y",
        "ROUND_NUMBER": 3,
        "MEMBER_NUMBER": "M0042",
        "NON_CLEARING_MEMBER_NUMBER": "NC042",
    }, arrays={"issues": issues})

    parsed = parse(raw, registry)
    assert parsed.fields["ROUND_NUMBER"] == 3
    assert len(parsed.arrays["issues"]) == 20
    assert parsed.arrays["issues"][5]["ASK_TRADING_VOLUME"] == 500
    assert parsed.arrays["issues"][5]["BID_TRADING_VOLUME"] == 1000
    assert parsed.arrays["issues"][19]["TRADING_VOLUME_WEIGHTED_AVERAGE_PRICE"] == 10_019


def test_decimal_point_numeric_format(registry):
    """Real samples emit TRD_MRGN_RT with a literal '.' separator
    (e.g. '000015.220000') instead of the sign-byte + implicit-decimal
    form. Parser must handle both; here we hand-craft a record where
    the TRD_MRGN_RT slice uses the dotted form."""
    schema = registry.get("TCSMIH42101")
    # Build a record normally, then overwrite one TRD_MRGN_RT slot with
    # a dotted-form value and confirm it parses.
    from tests.builder import build_record

    issues = [
        {"MARKET_IDENTIFICATION": "STK", "SECURITIES_GROUP_IDENTIFICATION": "SG",
         "ISSUE_CODE": f"KR{i:010d}", "ISU_KOR_ABBRV": "x",
         "TRD_MRGN_RT": Decimal(0)}
        for i in range(16)
    ]
    raw = bytearray(build_record(schema, fields={
        "TRANSACTION_CODE": "TCSMIH42101",
        "TRANSMIT_DATE": "20260423",
        "EMSG_COMPLT_YN": "N",
        "MESSAGE_SEQUENCE_NUMBER": 1,
    }, arrays={"issues": issues}))

    # Find the first issue's TRD_MRGN_RT slice and replace it with
    # dotted form. Array starts at offset 31, element length 70,
    # TRD_MRGN_RT sits at element-offset 3+2+12+40 = 57, length 13.
    arr_start = 31
    elem_trd_offset = 3 + 2 + 12 + 40
    slot = arr_start + elem_trd_offset
    raw[slot : slot + 13] = b"000015.220000"

    parsed = parse(bytes(raw), registry)
    assert parsed.arrays["issues"][0]["TRD_MRGN_RT"] == Decimal("15.220000")


def test_negative_numeric_field(registry):
    """Required-value fields carry a leading sign byte; confirm '-' roundtrips."""
    schema = registry.get("TCSMIH43301")
    raw = build_record(schema, fields={
        "MESSAGE_SEQUENCE_NUMBER": 1,
        "TRANSACTION_CODE": "TCSMIH43301",
        "TRANSMIT_DATE": "20260424",
        "EMSG_COMPLT_YN": "Y",
        "CLEARING_SETTLEMENT_MARKET_IDENTIFICATION": "SPT",
        "MEMBER_NUMBER": "M0001",
        "TRST_REQVAL": Decimal("-1234567.890"),
        "PRINC_REQVAL": Decimal("-2000000.000"),
        "REQVAL_AGG": Decimal("-3234567.890"),
    })
    parsed = parse(raw, registry)
    assert parsed.fields["TRST_REQVAL"] == Decimal("-1234567.890")
    assert parsed.fields["PRINC_REQVAL"] == Decimal("-2000000.000")
    assert parsed.fields["REQVAL_AGG"] == Decimal("-3234567.890")


def test_over_short_type_code(registry):
    schema = registry.get("TCSMIH42301")
    raw = build_record(schema, fields={
        "MESSAGE_SEQUENCE_NUMBER": 1,
        "TRANSACTION_CODE": "TCSMIH42301",
        "TRANSMIT_DATE": "20260424",
        "EMSG_COMPLT_YN": "Y",
        "OVRES_SHORTS_TYPE_CODE": OvresShortsTypeCode.SHORT.value,
        "CASHABLE_ASSET_TRADING_MARGIN_OVRES_SHORTS_TYPE_CODE": OvresShortsTypeCode.EQUAL.value,
    })
    parsed = parse(raw, registry)
    assert parsed.fields["OVRES_SHORTS_TYPE_CODE"] == "2"
    assert parsed.fields["CASHABLE_ASSET_TRADING_MARGIN_OVRES_SHORTS_TYPE_CODE"] == "3"


def test_unknown_transaction_code_raises(registry):
    # 22-byte prefix: 11 bytes msg seq + 11 bytes tr code
    fake = b"0" * 11 + b"TCSUNKNOWN!" + b" " * (1200 - 22)
    assert len(fake) == 1200
    with pytest.raises(UnknownMessageType) as excinfo:
        parse(fake, registry)
    assert excinfo.value.transaction_code == "TCSUNKNOWN!"


def test_wrong_record_length_raises(registry):
    schema = registry.get("TCSMIH42201")
    raw = build_record(schema, fields={"TRANSACTION_CODE": "TCSMIH42201"})
    with pytest.raises(FieldDecodeError):
        parse(raw[:1000], registry)


def test_peek_transaction_code(registry):
    parser = Parser(registry)
    schema = registry.get("TCSMIH43201")
    raw = build_record(schema, fields={"TRANSACTION_CODE": "TCSMIH43201"})
    assert parser.peek_transaction_code(raw) == "TCSMIH43201"
    assert parser.peek_transaction_code(raw[:22]) == "TCSMIH43201"


def test_peek_raises_on_short_input(registry):
    parser = Parser(registry)
    with pytest.raises(FieldDecodeError):
        parser.peek_transaction_code(b"too short")


def test_schema_sign_byte_validation(registry):
    """Ensure every numeric field's int_digits+frac_digits+sign fits exactly."""
    for code in registry.codes():
        schema = registry.get(code)
        for item in schema.layout:
            fields = item.fields if hasattr(item, "fields") else [item]
            for fld in fields:
                if fld.is_numeric_formatted:
                    # This is what sign_bytes raises on if invalid:
                    assert fld.sign_bytes in (0, 1), (
                        f"{code}.{fld.name}: unexpected sign_bytes={fld.sign_bytes}"
                    )


def test_parse_schema_yaml_valid_and_invalid():
    from krx_parser.exceptions import SchemaValidationError
    from krx_parser.registry import parse_schema_yaml

    ok = """
transaction_code: TCSMIHTEST1
description: test
market: equity
encoding: euc-kr
record_length: 32
layout:
  - kind: field
    name: MESSAGE_SEQUENCE_NUMBER
    kor_name: x
    type: Long
    length: 11
  - kind: field
    name: TRANSACTION_CODE
    kor_name: x
    type: String
    length: 11
  - kind: field
    name: FILLER_VALUE
    kor_name: x
    type: String
    length: 10
"""
    sch = parse_schema_yaml(ok)
    assert sch.transaction_code == "TCSMIHTEST1"
    assert sch.record_length == 32

    # Mismatch: declared 1200 but layout sums to 32.
    bad = ok.replace("record_length: 32", "record_length: 1200")
    with pytest.raises(SchemaValidationError):
        parse_schema_yaml(bad)

    # Not a mapping at all.
    with pytest.raises(SchemaValidationError):
        parse_schema_yaml("- just\n- a\n- list\n")

    # YAML syntax error.
    with pytest.raises(SchemaValidationError):
        parse_schema_yaml(": bad\n  - nope")


def test_schema_file_crud(tmp_path):
    from krx_parser.exceptions import SchemaValidationError
    from krx_parser.registry import (
        NEW_SCHEMA_TEMPLATE,
        delete_schema_file,
        list_schema_files,
        read_schema_text,
        write_schema_text,
    )

    # Write a valid custom schema.
    schema = write_schema_text(NEW_SCHEMA_TEMPLATE, schema_dir=tmp_path)
    assert schema.transaction_code == "TCSMIH00000"
    assert len(list_schema_files(tmp_path)) == 1
    assert "transaction_code: TCSMIH00000" in read_schema_text(
        "TCSMIH00000", schema_dir=tmp_path
    )

    # expected_transaction_code mismatch rejects.
    with pytest.raises(SchemaValidationError):
        write_schema_text(
            NEW_SCHEMA_TEMPLATE,
            schema_dir=tmp_path,
            expected_transaction_code="TCSMIH99999",
        )

    # Delete.
    assert delete_schema_file("TCSMIH00000", schema_dir=tmp_path) is True
    assert delete_schema_file("TCSMIH00000", schema_dir=tmp_path) is False
    assert list_schema_files(tmp_path) == []


def test_duplicate_schema_detection(tmp_path):
    from krx_parser.registry import load_registry

    (tmp_path / "a.yaml").write_text(_minimal_schema_yaml("TCSMIH42201"), encoding="utf-8")
    (tmp_path / "b.yaml").write_text(_minimal_schema_yaml("TCSMIH42201"), encoding="utf-8")
    with pytest.raises(SchemaValidationError):
        load_registry(tmp_path)


def _minimal_schema_yaml(code: str) -> str:
    return f"""\
transaction_code: {code}
description: test
market: equity
encoding: euc-kr
record_length: 32
layout:
  - kind: field
    name: MESSAGE_SEQUENCE_NUMBER
    kor_name: x
    type: Long
    length: 11
  - kind: field
    name: TRANSACTION_CODE
    kor_name: x
    type: String
    length: 11
  - kind: field
    name: FILLER_VALUE
    kor_name: x
    type: String
    length: 10
"""
