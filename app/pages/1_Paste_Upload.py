"""Paste or upload raw record bytes; preview; save to DB.

Auto-detects KMAPv2-framed logs vs. already-extracted record streams.
Encrypted frames are saved as `raw_messages` with `parse_status='error'`;
they cannot be parsed without the decryption routine (see §M5 plan).
"""

from __future__ import annotations

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
st.title("Paste / Upload")

parser = get_parser()
registry = get_registry()

tab_paste, tab_file = st.tabs(["Paste text", "Upload file"])

with tab_paste:
    st.caption(
        "Paste raw record text below. The page auto-detects KMAPv2-framed "
        "logs (e.g. producer stdout captures) — otherwise it treats input "
        "as concatenated pre-extracted record bytes."
    )
    text = st.text_area("Paste", height=220, key="paste_text")
    source = st.text_input("Source label", value="paste", key="paste_source")
    paste_submit = st.button("Preview", key="paste_preview")
    if paste_submit and text:
        st.session_state["input_payload"] = sanitize_paste(text)
        st.session_state["input_source"] = source

with tab_file:
    uploaded = st.file_uploader("Upload log file", type=None, key="upload_file")
    upload_source = st.text_input(
        "Source label",
        value=uploaded.name if uploaded else "",
        key="upload_source",
    )
    if uploaded is not None:
        st.session_state["input_payload"] = uploaded.getvalue()
        st.session_state["input_source"] = upload_source or uploaded.name

payload: bytes | None = st.session_state.get("input_payload")
source: str | None = st.session_state.get("input_source")

if payload:
    st.divider()
    st.subheader("Preview")
    st.caption(f"{len(payload):,} bytes received.")

    frames, records = extract(payload)

    if frames:
        encrypted = [f for f in frames if f.header.is_encrypted]
        plain = [f for f in frames if not f.header.is_encrypted]
        st.caption(
            f"Detected **{len(frames)}** KMAPv2 frame(s) — "
            f"{len(plain)} plaintext, {len(encrypted)} encrypted."
        )

        from collections import Counter

        tr_counts = Counter(f.header.message_type for f in frames)
        st.dataframe(
            [
                {
                    "TR code": tr,
                    "frames": n,
                    "encrypted": sum(
                        1
                        for f in frames
                        if f.header.message_type == tr and f.header.is_encrypted
                    ),
                    "in schema": tr in registry,
                }
                for tr, n in tr_counts.most_common()
            ],
            use_container_width=True,
            hide_index=True,
        )

        if encrypted:
            st.warning(
                f"{len(encrypted)} encrypted frame(s) cannot be parsed until "
                "a decryption routine is available. They will be saved to "
                "`raw_messages` with `parse_status='error'`."
            )

        if plain:
            with st.expander(f"Plaintext preview — first frame ({plain[0].header.message_type})"):
                first = plain[0]
                if first.header.message_type in registry:
                    parsed = parser.parse(first.data)
                    schema = registry.get(parsed.transaction_code)
                    labels = korean_labels(schema)
                    st.dataframe(
                        [
                            {"필드": labels.get(k, k), "EN": k, "값": str(v)}
                            for k, v in parsed.fields.items()
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info(
                        f"{first.header.message_type} is not in the schema "
                        "registry — will land as UnknownMessageType."
                    )

        if st.button("Save to database", type="primary"):
            with repo_scope() as repo:
                results = repo.ingest_frames(frames, source=source or "paste")
            n_ok = sum(1 for r in results if isinstance(r, StoredMessage))
            n_err = sum(1 for r in results if isinstance(r, RawMessage))
            st.success(
                f"Saved {n_ok} parsed record(s) and {n_err} error row(s) "
                f"(encrypted + unparseable)."
            )
            st.session_state.pop("input_payload", None)
            st.session_state.pop("input_source", None)

    else:
        st.caption(f"Detected **{len(records)}** complete record(s) (no KMAPv2 framing).")

        if records:
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
            st.dataframe(preview_rows, use_container_width=True, hide_index=True)

            if preview_rows and "error" not in preview_rows[0]:
                first = parser.parse(records[0])
                schema = registry.get(first.transaction_code)
                labels = korean_labels(schema)
                with st.expander(f"Detail — record 1 ({first.transaction_code})"):
                    st.dataframe(
                        [
                            {"필드": labels.get(k, k), "EN": k, "값": str(v)}
                            for k, v in first.fields.items()
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

            if st.button("Save to database", type="primary"):
                with repo_scope() as repo:
                    results = repo.ingest_many(records, source=source or "paste")
                n_ok = sum(1 for r in results if isinstance(r, StoredMessage))
                n_err = sum(1 for r in results if isinstance(r, RawMessage))
                st.success(
                    f"Saved {n_ok} parsed record(s) and {n_err} unparseable row(s)."
                )
                st.session_state.pop("input_payload", None)
                st.session_state.pop("input_source", None)
