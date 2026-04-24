"""Browse registered TR-code schemas with Korean labels."""

from __future__ import annotations

import streamlit as st

from app.helpers import get_registry
from krx_parser.schema import Array, Field

st.set_page_config(page_title="Schemas", page_icon="📘", layout="wide")
st.title("Registered schemas")

registry = get_registry()

selected = st.selectbox("TR code", registry.codes())

schema = registry.get(selected)

st.caption(schema.description)
cols = st.columns(3)
cols[0].metric("Market", schema.market)
cols[1].metric("Encoding", schema.encoding)
cols[2].metric("Record length", f"{schema.record_length:,} bytes")

st.divider()

st.markdown("### Layout")

def _flat_rows():
    seq = 0
    for item in schema.layout:
        if isinstance(item, Field):
            seq += 1
            yield {
                "Seq": seq,
                "필드 (KR)": item.kor_name,
                "설명": item.kor_description,
                "Field (EN)": item.name,
                "Type": item.type,
                "Len": item.length,
                "I.F": _ifs(item),
                "Offset": item.offset,
            }
        elif isinstance(item, Array):
            seq += 1
            yield {
                "Seq": seq,
                "필드 (KR)": f"(배열) {item.name}",
                "설명": f"{item.count} × {item.record_length} B",
                "Field (EN)": f"[{item.name}]",
                "Type": "Array",
                "Len": item.total_length,
                "I.F": "",
                "Offset": item.offset,
            }


def _ifs(fld: Field) -> str:
    if fld.int_digits is not None and fld.frac_digits is not None:
        return f"{fld.int_digits}.{fld.frac_digits}"
    return ""


st.dataframe(list(_flat_rows()), use_container_width=True, hide_index=True)

# Expand each array to show its per-element fields.
for item in schema.layout:
    if isinstance(item, Array):
        with st.expander(f"Array · {item.name} — {item.count} × {item.record_length} B"):
            st.dataframe(
                [
                    {
                        "Seq": i + 1,
                        "필드 (KR)": f.kor_name,
                        "설명": f.kor_description,
                        "Field (EN)": f.name,
                        "Type": f.type,
                        "Len": f.length,
                        "I.F": _ifs(f),
                        "Offset (within element)": f.offset,
                    }
                    for i, f in enumerate(item.fields)
                ],
                use_container_width=True,
                hide_index=True,
            )
