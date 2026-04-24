"""Paste or upload raw record bytes; preview; save to DB."""

from __future__ import annotations

import streamlit as st

from app.helpers import (
    get_parser,
    get_registry,
    iter_records,
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
        "Paste raw record text below. Expected: concatenated fixed-width "
        "records (1,200 bytes per record for TCSMIH4xxxx)."
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

    records = list(iter_records(payload, parser))
    st.caption(f"Detected **{len(records)}** complete record(s).")

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

        # Per-record detail of the first preview row
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

    if st.button("Save to database", type="primary", disabled=not records):
        with repo_scope() as repo:
            results = repo.ingest_many(records, source=source or "paste")

        n_ok = sum(1 for r in results if isinstance(r, StoredMessage))
        n_err = sum(1 for r in results if isinstance(r, RawMessage))
        st.success(f"Saved {n_ok} parsed record(s) and {n_err} unparseable row(s).")
        if n_err:
            with st.expander("Errors"):
                for r in results:
                    if isinstance(r, RawMessage):
                        st.text(r.error_detail or "(no detail)")
        # Clear buffered input so the user can move on.
        st.session_state.pop("input_payload", None)
        st.session_state.pop("input_source", None)
