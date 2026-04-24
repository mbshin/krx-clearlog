"""Filter parsed records by TR code, transmit date, member, underlying asset."""

from __future__ import annotations

import streamlit as st

from app.helpers import get_registry, korean_labels, repo_scope

st.set_page_config(page_title="Lookup", page_icon="🔎", layout="wide")
st.title("Lookup")

registry = get_registry()
tr_codes = ["(all)"] + registry.codes()

col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    tr_code = st.selectbox("TR code", tr_codes, index=0)
    member_number = st.text_input("MEMBER_NUMBER 회원번호")
with col2:
    date_from = st.text_input("Transmit date from (YYYYMMDD)")
    date_to = st.text_input("Transmit date to (YYYYMMDD)")
with col3:
    underlying = st.text_input("UNDERLYING_ASSET_CODE 기초자산코드")
    limit = st.number_input("Limit", min_value=10, max_value=1000, value=100, step=10)

st.divider()

with repo_scope() as repo:
    rows = repo.search(
        transaction_code=None if tr_code == "(all)" else tr_code,
        transmit_date_from=date_from or None,
        transmit_date_to=date_to or None,
        member_number=member_number or None,
        underlying_asset_code=underlying or None,
        limit=int(limit),
    )

st.caption(f"{len(rows)} result(s).")

if rows:
    table_rows = []
    for row in rows:
        labels = (
            korean_labels(registry.get(row.transaction_code))
            if row.transaction_code in registry
            else {}
        )
        member = row.fields.get("MEMBER_NUMBER", "")
        table_rows.append({
            "ID": row.parsed_id,
            "TR": row.transaction_code,
            "일련번호": row.message_sequence_number,
            "전송일자": row.transmit_date,
            "완료": row.emsg_complt_yn,
            "회원번호": member,
            "소스": row.source,
            "수신": row.received_at.isoformat(sep=" ", timespec="seconds"),
            "_labels": labels,  # retained for potential downstream use
        })

    # Drop internal-only key before rendering.
    for r in table_rows:
        r.pop("_labels", None)

    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    st.info(
        "Open the **Inspect** page and enter an ID (from the table above) "
        "to see the full field-by-field breakdown of a record."
    )
