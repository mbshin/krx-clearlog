"""KRX 청산결제 log viewer — landing page.

Run with:

    streamlit run app/main.py
"""

from __future__ import annotations

import streamlit as st

from app.helpers import get_registry, repo_scope
from krx_parser.settings import get_settings

st.set_page_config(
    page_title="KRX 청산결제 Log Viewer",
    page_icon="📑",
    layout="wide",
)

st.title("KRX 청산결제 Log Viewer")
st.caption(
    "Parser + lookup UI for KRX clearing-and-settlement messages "
    "(TCSMIH41xxx — TCSMIH43xxx). See `spec/messages.md` for the "
    "full field layouts."
)

settings = get_settings()
registry = get_registry()

col1, col2 = st.columns(2)
with col1:
    st.metric("Registered TR codes", len(registry))
with col2:
    st.metric("Database", settings.database_url)

st.divider()

st.subheader("Ingestion summary")
try:
    with repo_scope() as repo:
        counts = repo.count_by_transaction_code()
    if counts:
        rows = sorted(counts.items())
        st.dataframe(
            {"TR code": [tr for tr, _ in rows], "Records": [n for _, n in rows]},
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "No messages in the database yet. Head to **Paste / Upload** "
            "to ingest some records."
        )
except Exception as exc:  # noqa: BLE001
    st.error(f"Database error: {exc}")

st.divider()

st.subheader("Pages")
st.markdown(
    """
- **1 · Paste / Upload** — paste raw record bytes or upload a file;
  preview, then save to the database.
- **2 · Lookup** — search parsed records by TR code, transmit date
  range, member number, or underlying asset code.
- **3 · Inspect** — full field-by-field view of a single parsed record,
  plus the raw payload.
- **4 · Schemas** — browse the 11 registered TR-code layouts with
  Korean field labels.
    """
)

with st.expander("Known limitations"):
    st.markdown(
        """
- **Frame extraction not built yet.** Real KRX logs wrap each record
  in a `KMAPv2.0` envelope (see `spec/messages.md` §0). Paste / Upload
  currently expects already-extracted record bytes (concatenated back
  to back). A frame-stripping adapter is a follow-on task.
- **TR-code scope.** Only 증거금 messages (TCSMIH41xxx–43xxx) are
  in-scope for v1; anything else is rejected as `UnknownMessageType`.
        """
    )
