"""Filter parsed records by TR code, transmit date, member, underlying asset.

Filter state is mirrored in URL query parameters so any set of
filters is shareable / bookmarkable. Supported keys:

    ?tr=TCSMIH42101
    ?from=20260423 &to=20260425
    ?member=00045
    ?underlying=HK
    ?limit=200

Empty / default values are omitted from the URL.
"""

from __future__ import annotations

import streamlit as st

from app.helpers import get_registry, repo_scope

st.set_page_config(page_title="Lookup", page_icon="🔎", layout="wide")
st.title("🔎 Lookup")
st.caption(
    "Filter persisted parsed records. URL reflects current filters — "
    "copy the link to share a view."
)

registry = get_registry()
tr_codes = ["(all)"] + registry.codes()

# --- read query params (defaults) ----------------------------------------
qp = st.query_params
tr_default = qp.get("tr", "(all)")
if tr_default not in tr_codes:
    tr_default = "(all)"
date_from_default = qp.get("from", "")
date_to_default = qp.get("to", "")
member_default = qp.get("member", "")
underlying_default = qp.get("underlying", "")
try:
    limit_default = int(qp.get("limit", "100"))
except ValueError:
    limit_default = 100
limit_default = max(10, min(1000, limit_default))


def _tr_label(code: str) -> str:
    if code == "(all)":
        return "(all)"
    schema = registry.get(code)
    return f"{code} — {schema.description}"


with st.container(border=True):
    st.markdown("#### Filters")
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        tr_code = st.selectbox(
            "TR code",
            tr_codes,
            index=tr_codes.index(tr_default),
            format_func=_tr_label,
            key="flt_tr",
        )
        member_number = st.text_input(
            "MEMBER_NUMBER · 회원번호",
            value=member_default,
            key="flt_member",
        )
    with col2:
        date_from = st.text_input(
            "Transmit date from (YYYYMMDD)",
            value=date_from_default,
            key="flt_from",
        )
        date_to = st.text_input(
            "Transmit date to (YYYYMMDD)",
            value=date_to_default,
            key="flt_to",
        )
    with col3:
        underlying = st.text_input(
            "UNDERLYING_ASSET_CODE · 기초자산코드",
            value=underlying_default,
            key="flt_underlying",
        )
        limit = st.number_input(
            "Limit",
            min_value=10,
            max_value=1000,
            value=limit_default,
            step=10,
            key="flt_limit",
        )

    lb, rb = st.columns([1, 1])
    with lb:
        if st.button("🧹 Clear filters", key="flt_clear"):
            st.query_params.clear()
            for k in (
                "flt_tr",
                "flt_member",
                "flt_from",
                "flt_to",
                "flt_underlying",
                "flt_limit",
            ):
                st.session_state.pop(k, None)
            st.rerun()

# --- sync query params back (only non-default entries) -------------------
new_qp: dict[str, str] = {}
if tr_code != "(all)":
    new_qp["tr"] = tr_code
if date_from:
    new_qp["from"] = date_from
if date_to:
    new_qp["to"] = date_to
if member_number:
    new_qp["member"] = member_number
if underlying:
    new_qp["underlying"] = underlying
if int(limit) != 100:
    new_qp["limit"] = str(int(limit))
# Only write if the URL would actually change; avoids a rerun-loop.
if dict(st.query_params) != new_qp:
    st.query_params.clear()
    for k, v in new_qp.items():
        st.query_params[k] = v

# --- query ---------------------------------------------------------------
with repo_scope() as repo:
    rows = repo.search(
        transaction_code=None if tr_code == "(all)" else tr_code,
        transmit_date_from=date_from or None,
        transmit_date_to=date_to or None,
        member_number=member_number or None,
        underlying_asset_code=underlying or None,
        limit=int(limit),
    )

st.divider()

mc1, mc2 = st.columns(2)
mc1.metric("Results", f"{len(rows):,}")
mc2.metric("Limit", f"{int(limit):,}")

if rows:
    # Snapshot filter URL for Inspect's Back button.
    st.session_state["lookup_return_qp"] = dict(st.query_params)

    # Weights for a 9-column layout: ID | TR | 일련번호 | 전송일자 |
    # 완료 | 회원번호 | 소스 | 수신 | [Open]
    col_widths = [0.7, 1.5, 1.1, 1.0, 0.4, 0.8, 2.5, 1.8, 1.0]
    headers = [
        "ID", "TR", "일련번호", "전송일자", "완료",
        "회원번호", "소스", "수신", "",
    ]

    with st.container(border=True):
        head = st.columns(col_widths)
        for c, h in zip(head, headers, strict=True):
            c.markdown(f"**{h}**")
        st.divider()

        for row in rows:
            c = st.columns(col_widths)
            member = row.fields.get("MEMBER_NUMBER", "") or ""
            c[0].write(row.parsed_id)
            c[1].write(row.transaction_code)
            c[2].write(row.message_sequence_number)
            c[3].write(row.transmit_date)
            c[4].write(row.emsg_complt_yn)
            c[5].write(member)
            c[6].write(row.source)
            c[7].write(row.received_at.isoformat(sep=" ", timespec="seconds"))
            if c[8].button("🔬 Open", key=f"open_{row.parsed_id}", width="stretch"):
                st.session_state["inspect_id"] = int(row.parsed_id)
                st.session_state["lookup_return_qp"] = dict(st.query_params)
                st.switch_page("pages/3_Inspect.py")
else:
    st.info("No matches. Adjust filters or ingest more records in **📥 Upload**.")
