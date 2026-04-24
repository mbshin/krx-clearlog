"""Full field-by-field view of a single parsed record."""

from __future__ import annotations

import streamlit as st

from app.helpers import get_registry, iter_arrays, iter_flat_fields, repo_scope


def _format(value) -> str:
    if value is None:
        return ""
    return str(value)


def _hex_preview(payload: bytes, per_line: int = 32) -> str:
    lines = []
    for i in range(0, len(payload), per_line):
        chunk = payload[i : i + per_line]
        hex_str = " ".join(f"{b:02x}" for b in chunk)
        lines.append(f"{i:06x}  {hex_str}")
    return "\n".join(lines)


st.set_page_config(page_title="Inspect", page_icon="🔬", layout="wide")

back_col, title_col = st.columns([1, 5])
with back_col:
    if st.button(
        "← Back to Lookup",
        width="stretch",
        type="primary",
        key="back_to_lookup",
    ):
        # Restore the filter URL we captured before navigating here so
        # the user lands on the exact same filtered view.
        saved_qp = st.session_state.get("lookup_return_qp")
        st.query_params.clear()
        if saved_qp:
            for k, v in saved_qp.items():
                st.query_params[k] = v
        st.switch_page("pages/2_Lookup.py")
with title_col:
    st.title("🔬 Inspect")

registry = get_registry()

qp_id = st.query_params.get("id")
default_id = 0
if qp_id and qp_id.isdigit():
    default_id = int(qp_id)
elif st.session_state.get("inspect_id"):
    default_id = int(st.session_state["inspect_id"])
parsed_id = st.number_input(
    "Parsed message ID",
    min_value=0,
    value=default_id,
    step=1,
    help="ID column from the Lookup page.",
)

if not parsed_id:
    st.info("Enter an ID above, or open this page via the 🔎 link on **Lookup**.")
    st.stop()

with repo_scope() as repo:
    stored = repo.get(int(parsed_id))

if stored is None:
    st.error(f"No parsed message with id={parsed_id}.")
    st.stop()

schema = registry.get(stored.transaction_code) if stored.transaction_code in registry else None

with st.container(border=True):
    header_cols = st.columns([2, 1, 1])
    header_cols[0].markdown(
        f"### {stored.transaction_code}\n"
        + (f"*{schema.description}*" if schema else "*(schema not registered)*")
    )
    header_cols[1].metric("일련번호", stored.message_sequence_number)
    header_cols[2].metric("전송일자", stored.transmit_date)

    meta = st.columns(4)
    meta[0].metric("완료여부", stored.emsg_complt_yn)
    meta[1].metric("Parsed ID", stored.parsed_id)
    meta[2].metric("Raw ID", stored.raw_id)
    meta[3].metric("Source", stored.source)

tab_body, tab_raw = st.tabs(["📋 Fields & Arrays", "🗂️ Raw payload"])

with tab_body:
    if schema is None:
        st.warning("TR code not in schema — raw fields below.")
        st.json(stored.fields)
    else:
        st.markdown("#### Fields")
        flat_rows = [
            {
                "Seq": i + 1,
                "필드 (KR)": fld.kor_name,
                "Field (EN)": fld.name,
                "Type": fld.type,
                "Len": fld.length,
                "값": _format(stored.fields.get(fld.name)),
            }
            for i, fld in enumerate(iter_flat_fields(schema))
        ]
        st.dataframe(flat_rows, width="stretch", hide_index=True)

        arrays = list(iter_arrays(schema))
        if arrays:
            st.markdown("#### Arrays")
            for arr in arrays:
                records = stored.arrays.get(arr.name, [])
                with st.container(border=True):
                    st.markdown(
                        f"**`{arr.name}`** — {len(records)} × {arr.record_length} bytes "
                        f"(declared: {arr.count})"
                    )
                    st.caption(
                        ", ".join(f"{fld.kor_name} = `{fld.name}`" for fld in arr.fields)
                    )
                    if records:
                        data_rows = [
                            {fld.kor_name: _format(rec.get(fld.name)) for fld in arr.fields}
                            for rec in records
                        ]
                        st.dataframe(data_rows, width="stretch", hide_index=True)
                    else:
                        st.caption("(no elements)")

with tab_raw:
    st.caption(f"{len(stored.payload):,} bytes")
    col_hex, col_text = st.columns(2)
    with col_hex:
        st.markdown("**Hex**")
        st.code(_hex_preview(stored.payload[:1024]), language="text")
        if len(stored.payload) > 1024:
            st.caption(f"(first 1,024 of {len(stored.payload):,} bytes shown)")
    with col_text:
        st.markdown("**ASCII / EUC-KR (best-effort)**")
        try:
            st.code(
                stored.payload[:1024].decode("euc-kr", errors="replace"),
                language="text",
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"decode failed: {exc}")
