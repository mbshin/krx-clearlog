"""Admin — delete persisted records.

Destructive actions live on their own page behind explicit checkboxes
so a stray click can't wipe the DB.
"""

from __future__ import annotations

import streamlit as st

from app.helpers import get_registry, repo_scope

st.set_page_config(page_title="Admin", page_icon="🧹", layout="wide")
st.title("🧹 Admin")
st.caption("Delete persisted records. All actions require an explicit confirmation.")

registry = get_registry()

with repo_scope() as repo:
    counts = repo.count_by_transaction_code()
    raw_total = repo.count_raw()
    err_total = repo.count_errors()

c1, c2, c3 = st.columns(3)
c1.metric("parsed_messages", f"{sum(counts.values()):,}")
c2.metric("raw_messages", f"{raw_total:,}")
c3.metric("raw_messages (error)", f"{err_total:,}")

if counts:
    with st.container(border=True):
        st.markdown("#### By TR code")
        st.dataframe(
            sorted(
                (
                    {
                        "TR": tr,
                        "설명": (
                            registry.get(tr).description
                            if tr in registry
                            else "(unknown)"
                        ),
                        "records": n,
                    }
                    for tr, n in counts.items()
                ),
                key=lambda r: -r["records"],
            ),
            width="stretch",
            hide_index=True,
        )

st.divider()

with st.container(border=True):
    st.markdown("#### Delete by TR code")
    tr_choices = sorted(counts.keys())
    if tr_choices:
        tr_pick = st.selectbox(
            "TR code",
            tr_choices,
            format_func=lambda c: (
                f"{c} — {registry.get(c).description}"
                if c in registry
                else c
            ),
            key="admin_tr_pick",
        )
        confirm_tr = st.checkbox(
            f"I understand this will delete all {counts.get(tr_pick, 0)} "
            f"`{tr_pick}` record(s) and the linked raw payloads.",
            key="admin_tr_confirm",
        )
        if st.button("🗑️ Delete", disabled=not confirm_tr, key="admin_tr_btn"):
            with repo_scope() as repo:
                raw_n, parsed_n = repo.delete_by_transaction_code(tr_pick)
            st.success(f"Deleted {parsed_n} parsed and {raw_n} raw row(s) for {tr_pick}.")
            st.rerun()
    else:
        st.caption("No parsed rows to delete.")

with st.container(border=True):
    st.markdown("#### Delete only error rows (raw without a parsed row)")
    if err_total:
        confirm_err = st.checkbox(
            f"I understand this will delete {err_total} raw error row(s).",
            key="admin_err_confirm",
        )
        if st.button("🗑️ Delete error rows", disabled=not confirm_err, key="admin_err_btn"):
            with repo_scope() as repo:
                n = repo.delete_errors()
            st.success(f"Deleted {n} raw error row(s).")
            st.rerun()
    else:
        st.caption("No error rows present.")

with st.container(border=True):
    st.markdown("#### ⚠️ Truncate all tables")
    st.caption(
        "Removes every row from `parsed_messages` and `raw_messages`. "
        "Alembic schema is preserved; the next ingest starts from a clean DB."
    )
    confirm_all = st.checkbox(
        "I understand this will irreversibly delete ALL ingested records.",
        key="admin_all_confirm",
    )
    confirm_all_text = st.text_input(
        "Type `DELETE` to enable the button:", key="admin_all_text"
    )
    if st.button(
        "🧨 Truncate all",
        type="primary",
        disabled=not (confirm_all and confirm_all_text.strip() == "DELETE"),
        key="admin_all_btn",
    ):
        with repo_scope() as repo:
            raw_n, parsed_n = repo.delete_all()
        st.success(
            f"Deleted {parsed_n} parsed and {raw_n} raw row(s). DB is empty."
        )
        st.rerun()
