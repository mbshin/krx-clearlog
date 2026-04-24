"""KMAPv2.0 transport-frame parsing.

Real KRX logs wrap every message in an 82-byte `KMAPv2.0` envelope
followed by a DATA block whose length is carried in the header (and
whose layout is determined by the `MESSAGE_TYPE` TR code). The
samples under `samples/` arrive as application stdout/stderr streams
where each frame is embedded inside a log line (e.g.
`… RECV_0 [KMAPv2.0001200TCSMIH42101…] Len …`). This module strips
the envelope so downstream code can feed the DATA block into the
normal `Parser`.

Full header layout (see `spec/messages.md` §0) — 82 bytes total:

    8   MESSAGE_KIND                 always "KMAPv2.0"
    6   MESSAGE_LENGTH               length of DATA block (excludes this 82-B header)
   11   MESSAGE_TYPE                 TR code (TCSMIH…)
   11   SEQUENCE_NUMBER
    5   MEMBER_NUMBER
   10   CONNECT_RECV_MEMBER_NUMBER   optional
   10   REPLY_SEND_MEMBER_NUMBER     optional
   17   TRANSMIT_DATETIME            YYYYMMDDhhmmssSSS
    3   DATA_COUNT
    1   ENCRYPTED_YN                 Y/N
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from krx_parser.exceptions import FieldDecodeError

HEADER_LENGTH = 82
MARKER = b"KMAPv2.0"


@dataclass(frozen=True)
class KmapHeader:
    message_kind: str
    message_length: int
    message_type: str
    sequence_number: int
    member_number: str
    connect_recv_member_number: str
    reply_send_member_number: str
    transmit_datetime: str
    data_count: int
    encrypted_yn: str

    @property
    def is_encrypted(self) -> bool:
        return self.encrypted_yn.upper() == "Y"


@dataclass(frozen=True)
class KmapFrame:
    header: KmapHeader
    data: bytes
    raw: bytes  # header + data (no log-line prefix/suffix)

    @property
    def total_length(self) -> int:
        return HEADER_LENGTH + self.header.message_length


def parse_header(raw: bytes) -> KmapHeader:
    if len(raw) < HEADER_LENGTH:
        raise FieldDecodeError(
            "KMAPv2.header",
            raw,
            f"need {HEADER_LENGTH} bytes, got {len(raw)}",
        )

    # Layout is pure ASCII; no EUC-KR surprises in the envelope.
    try:
        text = raw[:HEADER_LENGTH].decode("ascii")
    except UnicodeDecodeError as exc:
        raise FieldDecodeError("KMAPv2.header", raw, f"ASCII decode failed: {exc}") from exc

    pos = 0

    def take(n: int) -> str:
        nonlocal pos
        chunk = text[pos : pos + n]
        pos += n
        return chunk

    message_kind = take(8)
    if message_kind != "KMAPv2.0":
        raise FieldDecodeError(
            "MESSAGE_KIND",
            raw,
            f"expected 'KMAPv2.0', got {message_kind!r}",
        )

    try:
        message_length = int(take(6))
        message_type = take(11).rstrip(" ")
        sequence_number = int(take(11))
        member_number = take(5).rstrip(" ")
        connect_recv = take(10).rstrip(" ")
        reply_send = take(10).rstrip(" ")
        transmit_datetime = take(17)
        data_count = int(take(3))
        encrypted_yn = take(1)
    except ValueError as exc:
        raise FieldDecodeError("KMAPv2.header", raw, f"Long parse: {exc}") from exc

    if encrypted_yn not in ("Y", "N"):
        raise FieldDecodeError(
            "ENCRYPTED_YN",
            raw,
            f"expected 'Y' or 'N', got {encrypted_yn!r}",
        )

    return KmapHeader(
        message_kind=message_kind,
        message_length=message_length,
        message_type=message_type,
        sequence_number=sequence_number,
        member_number=member_number,
        connect_recv_member_number=connect_recv,
        reply_send_member_number=reply_send,
        transmit_datetime=transmit_datetime,
        data_count=data_count,
        encrypted_yn=encrypted_yn,
    )


def parse_frame(raw: bytes) -> KmapFrame:
    """Parse a complete frame starting at offset 0 — no prefix scanning."""
    header = parse_header(raw)
    total = HEADER_LENGTH + header.message_length
    if len(raw) < total:
        raise FieldDecodeError(
            "KMAPv2.frame",
            raw,
            f"header declares {header.message_length}-byte DATA;"
            f" only {len(raw) - HEADER_LENGTH} bytes available",
        )
    data = bytes(raw[HEADER_LENGTH:total])
    return KmapFrame(header=header, data=data, raw=bytes(raw[:total]))


def iter_frames(
    stream: bytes | bytearray | memoryview,
    *,
    skip_invalid: bool = True,
    validate_data: bool = True,
) -> Iterator[KmapFrame]:
    """Scan a byte stream and yield every well-formed KMAPv2 frame.

    The stream may contain arbitrary prefix/suffix bytes (application
    log lines, whitespace, brackets) between frames. Each `KMAPv2.0`
    marker that yields a parseable header+DATA is emitted; invalid
    occurrences are either skipped (default) or raised.

    When `validate_data=True` (default), we require the DATA block's
    first 22 bytes to look like `MESSAGE_SEQUENCE_NUMBER` (11 ASCII
    digits) + `TRANSACTION_CODE` that matches the header's
    `MESSAGE_TYPE`. This rejects the `RECV_0 [KMAPv2.0…]` log-line
    copies whose "DATA" is actually log text (e.g. `] RECV_SEQ=…`)
    rather than the record payload. Without this check the scanner
    would advance past the encrypted RECV copy and miss the
    decrypted `TG_DecryptLOG` frame that follows.

    The scan is non-overlapping for valid frames: once a frame is
    emitted, the cursor advances past its DATA. For rejected
    candidates the cursor advances by one byte so the real frame
    trailing behind can still be found.
    """
    buf = bytes(stream) if not isinstance(stream, bytes) else stream
    n = len(buf)
    i = 0
    while i <= n - HEADER_LENGTH:
        marker_at = buf.find(MARKER, i)
        if marker_at < 0 or marker_at + HEADER_LENGTH > n:
            break
        try:
            header = parse_header(buf[marker_at : marker_at + HEADER_LENGTH])
        except FieldDecodeError:
            if skip_invalid:
                i = marker_at + 1
                continue
            raise

        total = HEADER_LENGTH + header.message_length
        if marker_at + total > n:
            break

        data = buf[marker_at + HEADER_LENGTH : marker_at + total]
        if validate_data and not _data_matches_header(data, header):
            if skip_invalid:
                i = marker_at + 1
                continue
            raise FieldDecodeError(
                "KMAPv2.frame",
                bytes(data[:32]),
                f"DATA does not begin with MSG_SEQ_NUM + {header.message_type!r}",
            )

        yield KmapFrame(
            header=header,
            data=bytes(data),
            raw=bytes(buf[marker_at : marker_at + total]),
        )
        i = marker_at + total


def _data_matches_header(data: bytes | memoryview, header: KmapHeader) -> bool:
    """True when DATA's body-level shared header (MSG_SEQ_NUM + TR code
    at bytes 0..22) is consistent with the KMAPv2 envelope.

    Used by `iter_frames` to discard log-line echoes of the RECV
    envelope whose "DATA" is actually downstream log text, not the
    record payload. Requires the payload to be at least 22 bytes;
    shorter DATA blocks are conservatively accepted (might be a
    non-TCSMIH message we don't know the shape of).
    """
    if len(data) < 22:
        return True
    if not all(0x30 <= b <= 0x39 for b in data[:11]):
        return False
    tr_slice = bytes(data[11:22])
    try:
        tr_text = tr_slice.decode("ascii").rstrip(" ")
    except UnicodeDecodeError:
        return False
    return tr_text == header.message_type
