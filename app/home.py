"""Landing page. Registered by `app/main.py` via `st.navigation`."""

from __future__ import annotations

import streamlit as st

from app.helpers import get_registry, repo_scope
from krx_parser.settings import get_settings

st.title("📑 KRX 청산결제 Log Viewer")
st.caption(
    "Parser + lookup UI for KRX clearing-and-settlement messages "
    "(TCSMIH41xxx — TCSMIH43xxx). Spec under `spec/messages.md`."
)

settings = get_settings()
registry = get_registry()

try:
    with repo_scope() as repo:
        counts = repo.count_by_transaction_code()
        raw_total = repo.count_raw()
        err_total = repo.count_errors()
except Exception as exc:  # noqa: BLE001
    counts, raw_total, err_total = {}, 0, 0
    st.error(f"Database error: {exc}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("TR codes registered", len(registry))
c2.metric("Parsed records", sum(counts.values()))
c3.metric("Raw records", raw_total)
c4.metric("Error rows", err_total)

st.divider()

with st.container(border=True):
    st.subheader("📊 Ingestion summary")
    if counts:
        rows = sorted(
            (
                {
                    "TR": tr,
                    "설명": registry.get(tr).description if tr in registry else "(unknown)",
                    "records": n,
                }
                for tr, n in counts.items()
            ),
            key=lambda r: -r["records"],
        )
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.info("Database is empty — head to **📥 Paste / Upload** to ingest some frames.")

st.divider()

with st.container(border=True):
    st.subheader("🧭 Pages")
    st.markdown(
        "- 📥 **Paste / Upload** — upload `.log` / `.log.gz` or paste record"
        " bytes. Auto-detects KMAPv2 framing; out-of-scope TR codes are"
        " skipped; parseable frames are saved.\n"
        "- 🔎 **Lookup** — filter parsed records by TR code, transmit date,"
        " 회원번호, 기초자산코드. Click the 🔎 icon to open Inspect.\n"
        "- 🔬 **Inspect** — full field-by-field breakdown of a parsed"
        " record: Korean labels, repeating-group sub-tables, raw payload.\n"
        "- 📘 **Schemas** — browse the 11 registered TR-code layouts with"
        " Korean descriptions.\n"
        "- 🧹 **Admin** — delete rows by TR code, clear error rows,"
        " truncate all."
    )

with st.expander("ℹ️ Known limitations"):
    st.markdown(
        """
- **KMAPv2 framing** is implemented; the scanner discards `RECV_0`
  log-line echoes whose DATA is log text rather than the record
  payload, then parses the `TG_DecryptLOG` plaintext copies.
- **TR-code scope:** only 증거금 messages (TCSMIH41xxx–43xxx) are
  in-scope. Other families (SCHHE*, TCSMIH26xxx, etc.) are skipped.
- **Active DB:** `""" + settings.database_url + """`
"""
    )
