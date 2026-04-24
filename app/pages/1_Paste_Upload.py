"""Paste or upload raw record bytes; preview; save to DB.

Auto-detects:
  - gzip input (decompresses in memory before scanning)
  - KMAPv2-framed logs vs. already-extracted record streams
Frames whose TR code isn't in the schema registry are skipped; frames
that match a schema but fail to parse (e.g. still-encrypted RECV copies)
land in raw_messages with parse_status='error'.
"""

from __future__ import annotations

import traceback
from collections import Counter

import streamlit as st

from app.helpers import (
    extract,
    get_parser,
    get_registry,
    korean_labels,
    repo_scope,
    sanitize_paste,
)
from krx_parser.db.models import RawMessage
from krx_parser.db.repository import StoredMessage

st.set_page_config(page_title="Paste / Upload", page_icon="📥", layout="wide")
st.title("📥 Paste / Upload")
st.caption(
    "Accepts raw KRX log bytes (KMAPv2-framed), concatenated "
    "pre-extracted records, or a `.gz` of either."
)

parser = get_parser()
registry = get_registry()

with st.container(border=True):
    st.markdown("#### 1 · Provide input")
    uploaded = st.file_uploader(
        "Upload a log file (.log / .log.gz / binary)",
        type=None,
        accept_multiple_files=False,
        help="Max ~500 MB.",
    )
    text = st.text_area(
        "Or paste text (concatenated records — not a binary log)",
        height=120,
    )
    source_label = st.text_input(
        "Source label (saved with each row)",
        value=uploaded.name if uploaded else "paste",
    )

payload: bytes | None = None
if uploaded is not None:
    try:
        payload = uploaded.getvalue()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to read uploaded file: {type(exc).__name__}: {exc}")
        payload = None
elif text.strip():
    payload = sanitize_paste(text)

if payload is None:
    st.info("Upload a file or paste text above to preview.")
    st.stop()

st.markdown("#### 2 · Preview")
st.caption(f"{len(payload):,} bytes received.")

try:
    frames, records, was_gzip = extract(payload)
except Exception as exc:  # noqa: BLE001
    st.error(f"extract() failed: {type(exc).__name__}: {exc}")
    st.code(traceback.format_exc(), language="text")
    st.stop()

if was_gzip:
    st.caption("Detected **gzip** input — decompressed in memory before scanning.")

if frames:
    encrypted = sum(1 for f in frames if f.header.is_encrypted)
    in_scope = sum(1 for f in frames if f.header.message_type in registry)
    st.caption(
        f"Detected **{len(frames):,}** KMAPv2 frame(s) — "
        f"{in_scope:,} in-scope for our schemas, "
        f"{encrypted:,} carry ENCRYPTED_YN=Y."
    )

    tr_counts = Counter(f.header.message_type for f in frames)
    st.dataframe(
        [
            {
                "TR code": tr,
                "frames": n,
                "encrypted (flag)": sum(
                    1 for f in frames
                    if f.header.message_type == tr and f.header.is_encrypted
                ),
                "in schema": tr in registry,
            }
            for tr, n in tr_counts.most_common()
        ],
        width="stretch",
        hide_index=True,
    )

    # Detail preview for the first in-scope frame we can parse.
    in_scope_frames = [f for f in frames if f.header.message_type in registry]
    if in_scope_frames:
        first = in_scope_frames[0]
        try:
            parsed_preview = parser.parse(first.data)
            schema = registry.get(parsed_preview.transaction_code)
            labels = korean_labels(schema)
            with st.expander(f"Detail — first in-scope frame ({first.header.message_type})"):
                st.dataframe(
                    [
                        {"필드": labels.get(k, k), "EN": k, "값": str(v)}
                        for k, v in parsed_preview.fields.items()
                    ],
                    width="stretch",
                    hide_index=True,
                )
        except Exception as exc:  # noqa: BLE001
            st.caption(
                f"First in-scope frame ({first.header.message_type}) "
                f"failed to parse: {exc}"
            )

    if st.button("Save to database", type="primary"):
        with st.spinner("Ingesting frames..."):
            with repo_scope() as repo:
                results, skipped = repo.ingest_frames(
                    frames, source=source_label or "upload"
                )
        n_ok = sum(1 for r in results if isinstance(r, StoredMessage))
        n_err = sum(1 for r in results if isinstance(r, RawMessage))
        st.success(
            f"Saved {n_ok:,} parsed record(s). "
            f"{n_err:,} in-scope frame(s) failed to parse. "
            f"{skipped:,} frame(s) skipped (TR code outside schema registry)."
        )

elif records:
    st.caption(f"Detected **{len(records):,}** complete record(s) (no KMAPv2 framing).")

    preview_n = st.slider(
        "Preview rows",
        min_value=1,
        max_value=min(50, len(records)),
        value=min(10, len(records)),
    )
    preview_rows = []
    for rec in records[:preview_n]:
        try:
            parsed = parser.parse(rec)
            preview_rows.append({
                "TR": parsed.transaction_code,
                "일련번호": parsed.message_sequence_number,
                "전송일자": parsed.transmit_date,
                "전문완료여부": parsed.emsg_complt_yn,
                "bytes": len(rec),
            })
        except Exception as exc:  # noqa: BLE001
            preview_rows.append({
                "TR": "?", "error": f"{type(exc).__name__}: {exc}",
            })
    st.dataframe(preview_rows, width="stretch", hide_index=True)

    if st.button("Save to database", type="primary"):
        with st.spinner("Ingesting records..."):
            with repo_scope() as repo:
                results = repo.ingest_many(records, source=source_label or "paste")
        n_ok = sum(1 for r in results if isinstance(r, StoredMessage))
        n_err = sum(1 for r in results if isinstance(r, RawMessage))
        st.success(f"Saved {n_ok:,} parsed record(s), {n_err:,} unparseable row(s).")

else:
    st.warning(
        "Could not detect any KMAPv2 frames or back-to-back records. "
        "First 120 bytes (hex):"
    )
    st.code(" ".join(f"{b:02x}" for b in payload[:120]))
