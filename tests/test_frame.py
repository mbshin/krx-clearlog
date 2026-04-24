from __future__ import annotations

import pytest

from krx_parser import iter_frames, parse_frame, parse_header
from krx_parser.exceptions import FieldDecodeError
from krx_parser.frame import HEADER_LENGTH, KmapHeader
from tests.builder import build_record


def build_header(
    *,
    tr_code: str,
    data_length: int,
    seq: int = 1,
    member: str = "M0001",
    connect: str = "",
    reply: str = "",
    datetime_str: str = "20260423150014856",
    data_count: int = 1,
    encrypted: str = "N",
) -> bytes:
    parts = [
        "KMAPv2.0",
        f"{data_length:06d}",
        tr_code.ljust(11, " "),
        f"{seq:011d}",
        member.ljust(5, " "),
        connect.ljust(10, " "),
        reply.ljust(10, " "),
        datetime_str,
        f"{data_count:03d}",
        encrypted,
    ]
    header = "".join(parts).encode("ascii")
    assert len(header) == HEADER_LENGTH
    return header


def test_parse_header_basic():
    header = parse_header(
        build_header(tr_code="TCSMIH42101", data_length=1200, seq=125, member="00045")
    )
    assert header.message_kind == "KMAPv2.0"
    assert header.message_length == 1200
    assert header.message_type == "TCSMIH42101"
    assert header.sequence_number == 125
    assert header.member_number == "00045"
    assert header.transmit_datetime == "20260423150014856"
    assert header.data_count == 1
    assert header.encrypted_yn == "N"
    assert header.is_encrypted is False


def test_parse_header_encrypted_flag():
    header = parse_header(
        build_header(tr_code="TCSMIH42101", data_length=1624, encrypted="Y")
    )
    assert header.message_length == 1624
    assert header.is_encrypted is True


def test_parse_header_rejects_non_kmap_marker():
    bad = b"WRONGv2.0" + b"000000" + b" " * (HEADER_LENGTH - 14)
    with pytest.raises(FieldDecodeError):
        parse_header(bad)


def test_parse_header_rejects_non_y_n_encryption():
    raw = bytearray(
        build_header(tr_code="TCSMIH42101", data_length=1200, encrypted="N")
    )
    raw[-1] = ord("Z")
    with pytest.raises(FieldDecodeError):
        parse_header(bytes(raw))


def test_parse_frame_plain(registry):
    schema = registry.get("TCSMIH42101")
    data = build_record(schema, fields={
        "TRANSACTION_CODE": "TCSMIH42101",
        "TRANSMIT_DATE": "20260423",
        "EMSG_COMPLT_YN": "Y",
        "MESSAGE_SEQUENCE_NUMBER": 7,
    })
    raw = build_header(tr_code="TCSMIH42101", data_length=len(data)) + data

    frame = parse_frame(raw)
    assert frame.header.message_type == "TCSMIH42101"
    assert frame.header.message_length == 1200
    assert frame.data == data
    assert frame.total_length == HEADER_LENGTH + 1200


def test_iter_frames_scans_over_log_noise(registry):
    schema = registry.get("TCSMIH42201")
    data1 = build_record(schema, fields={
        "TRANSACTION_CODE": "TCSMIH42201", "MEMBER_NUMBER": "M0001",
        "MESSAGE_SEQUENCE_NUMBER": 10, "TRANSMIT_DATE": "20260423", "EMSG_COMPLT_YN": "Y",
    })
    data2 = build_record(schema, fields={
        "TRANSACTION_CODE": "TCSMIH42201", "MEMBER_NUMBER": "M0002",
        "MESSAGE_SEQUENCE_NUMBER": 11, "TRANSMIT_DATE": "20260423", "EMSG_COMPLT_YN": "Y",
    })
    frame1 = build_header(tr_code="TCSMIH42201", data_length=1200, seq=10) + data1
    frame2 = build_header(tr_code="TCSMIH42201", data_length=1200, seq=11) + data2

    stream = (
        b"HH:MM:SS.uuuuuu LibProcEnv.c :InitExeArg :0293] I START\n"
        b"05:30:04 LibRelTr.c:IfS0_KrxRelTr:0780] I [LINE_0] RECV_0 ["
        + frame1
        + b"] Len=1282\n"
        b"random log noise\n"
        b"RECV_0 ["
        + frame2
        + b"] extra\n"
    )

    frames = list(iter_frames(stream))
    assert len(frames) == 2
    assert frames[0].header.sequence_number == 10
    assert frames[1].header.sequence_number == 11
    # Each yielded frame's DATA matches what we inserted — envelope is stripped.
    assert frames[0].data == data1
    assert frames[1].data == data2


def test_iter_frames_drops_truncated_trailer(registry):
    schema = registry.get("TCSMIH42201")
    data = build_record(schema, fields={"TRANSACTION_CODE": "TCSMIH42201"})
    # header claims 1200 bytes but we only include 400 — should be dropped
    truncated = build_header(tr_code="TCSMIH42201", data_length=1200) + data[:400]
    assert list(iter_frames(truncated)) == []


def test_iter_frames_skips_invalid_header():
    # Marker present but not followed by a valid header (non-digit length).
    stream = b"prefix KMAPv2.0ABCDEF some more bytes"
    assert list(iter_frames(stream)) == []


def test_parse_frame_rejects_truncated_data():
    raw = build_header(tr_code="TCSMIH42201", data_length=1200) + b"\x00" * 10
    with pytest.raises(FieldDecodeError):
        parse_frame(raw)


def test_iter_frames_then_parser_round_trip(registry):
    """End-to-end: build a multi-frame stream, scan it, parse each DATA."""
    from krx_parser import parse

    schema = registry.get("TCSMIH42201")
    frames_raw = b""
    expected_members: list[str] = []
    for i in range(5):
        member = f"M{i:04d}"
        expected_members.append(member)
        data = build_record(schema, fields={
            "TRANSACTION_CODE": "TCSMIH42201",
            "MEMBER_NUMBER": member,
            "MESSAGE_SEQUENCE_NUMBER": i + 1,
            "TRANSMIT_DATE": "20260423",
            "EMSG_COMPLT_YN": "Y",
        })
        frames_raw += (
            b"log prefix "
            + build_header(tr_code="TCSMIH42201", data_length=len(data), seq=i + 1)
            + data
            + b" log suffix\n"
        )

    got_members = []
    for frame in iter_frames(frames_raw):
        assert not frame.header.is_encrypted
        parsed = parse(frame.data, registry)
        got_members.append(parsed.fields["MEMBER_NUMBER"])
    assert got_members == expected_members


def test_header_fields_dataclass_are_frozen():
    header = KmapHeader(
        message_kind="KMAPv2.0", message_length=1200, message_type="TCSMIH42101",
        sequence_number=1, member_number="M0001",
        connect_recv_member_number="", reply_send_member_number="",
        transmit_datetime="20260423150014856", data_count=1, encrypted_yn="N",
    )
    with pytest.raises((AttributeError, TypeError, Exception)):  # frozen dataclass
        header.message_length = 9999  # type: ignore[misc]  # noqa: B017
