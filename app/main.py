"""Entry point — configures global page settings and builds the
navigation. Every nav entry has an explicit `title=` so sidebar
labels follow the same Title Case convention (Streamlit's default
would render `main.py` as lowercase `main` and keep underscores in
page filenames, which looked inconsistent next to single-word pages).

Run with:

    streamlit run app/main.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="KRX 청산결제 Log Viewer",
    page_icon="📑",
    layout="wide",
)

pages = [
    st.Page("home.py", title="Home", icon="📑", default=True),
    st.Page("pages/1_Paste_Upload.py", title="Upload", icon="📥"),
    st.Page("pages/2_Lookup.py", title="Lookup", icon="🔎"),
    st.Page("pages/3_Inspect.py", title="Inspect", icon="🔬"),
    st.Page("pages/4_Schemas.py", title="Schemas", icon="📘"),
    st.Page("pages/5_Admin.py", title="Admin", icon="🧹"),
]

pg = st.navigation(pages)
pg.run()
