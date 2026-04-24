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
st.title("Inspect")

registry = get_registry()

qp_id = st.query_params.get("id")
default_id = int(qp_id) if qp_id and qp_id.isdigit() else 0
parsed_id = st.number_input(
    "Parsed message ID",
    min_value=0,
    value=default_id,
    step=1,
    help="ID column from the Lookup page.",
)

if not parsed_id:
    st.info("Enter an ID above, or open this page from a Lookup row.")
    st.stop()

with repo_scope() as repo:
    stored = repo.get(int(parsed_id))

if stored is None:
    st.error(f"No parsed message with id={parsed_id}.")
    st.stop()

st.subheader(f"{stored.transaction_code} — 일련번호 {stored.message_sequence_number}")

meta_cols = st.columns(4)
meta_cols[0].metric("전송일자", stored.transmit_date)
meta_cols[1].metric("완료여부", stored.emsg_complt_yn)
meta_cols[2].metric("소스", stored.source)
meta_cols[3].metric("수신", stored.received_at.isoformat(sep=" ", timespec="seconds"))

st.divider()

if stored.transaction_code not in registry:
    st.warning(
        f"TR code {stored.transaction_code} is not registered; "
        "field labels unavailable."
    )
    st.json(stored.fields)
    if stored.arrays:
        st.json(stored.arrays)
else:
    schema = registry.get(stored.transaction_code)

    st.markdown("### Fields")
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
    st.dataframe(flat_rows, use_container_width=True, hide_index=True)

    for arr in iter_arrays(schema):
        records = stored.arrays.get(arr.name, [])
        st.markdown(f"### Array · {arr.name} ({len(records)} × {arr.record_length} bytes)")
        if not records:
            st.caption("(no elements)")
            continue
        # Pivot to KR-label columns
        columns = [fld.kor_name for fld in arr.fields]
        data_rows = []
        for rec in records:
            data_rows.append({
                fld.kor_name: _format(rec.get(fld.name)) for fld in arr.fields
            })
        st.dataframe(data_rows, use_container_width=True, hide_index=True)
        st.caption(", ".join(f"{fld.kor_name} = `{fld.name}`" for fld in arr.fields))

st.divider()

st.markdown("### Raw payload")
st.caption(f"{len(stored.payload):,} bytes")
col_hex, col_text = st.columns(2)
with col_hex:
    st.text("hex")
    st.code(_hex_preview(stored.payload), language="text")
with col_text:
    st.text("ASCII (best-effort EUC-KR)")
    try:
        st.code(stored.payload.decode("euc-kr", errors="replace"), language="text")
    except Exception as exc:  # noqa: BLE001
        st.error(f"decode failed: {exc}")
