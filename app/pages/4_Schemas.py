"""Browse + edit TR-code schemas (YAML CRUD)."""

from __future__ import annotations

import streamlit as st
from streamlit_ace import st_ace

from app.helpers import get_registry
from krx_parser.exceptions import SchemaValidationError
from krx_parser.registry import (
    NEW_SCHEMA_TEMPLATE,
    SCHEMA_DIR,
    delete_schema_file,
    parse_schema_yaml,
    read_schema_text,
    write_schema_text,
)
from krx_parser.schema import Array, Field

st.set_page_config(page_title="Schemas", page_icon="📘", layout="wide")
st.title("📘 Registered schemas")
st.caption(
    f"The TR-code layouts the parser can handle (directory: `{SCHEMA_DIR}`). "
    "Browse for reference, or switch to **Edit** to modify the YAML."
)

registry = get_registry()


def _tr_label(code: str) -> str:
    if code in registry:
        return f"{code} — {registry.get(code).description}"
    return code


def _ifs(fld: Field) -> str:
    if fld.int_digits is not None and fld.frac_digits is not None:
        return f"{fld.int_digits}.{fld.frac_digits}"
    return ""


def _invalidate_registry() -> None:
    """Force the cached registry to reload from disk on next page run."""
    get_registry.clear()


tab_browse, tab_edit = st.tabs(["📖 Browse", "✏️ Edit / Create"])

# ----------------------------------------------------------------------
# Browse
# ----------------------------------------------------------------------

with tab_browse:
    codes = registry.codes()
    if not codes:
        st.info("No schemas registered.")
    else:
        with st.container(border=True):
            selected = st.selectbox(
                "TR code", codes, format_func=_tr_label, key="browse_tr"
            )

        schema = registry.get(selected)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Market", schema.market)
        c2.metric("Encoding", schema.encoding)
        c3.metric("Record length", f"{schema.record_length:,} B")
        c4.metric("Top-level items", len(schema.layout))

        st.divider()

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

        st.markdown("### Layout")
        st.dataframe(list(_flat_rows()), width="stretch", hide_index=True)

        for item in schema.layout:
            if isinstance(item, Array):
                with st.expander(
                    f"📚 Array · `{item.name}` — {item.count} × {item.record_length} B"
                ):
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
                        width="stretch",
                        hide_index=True,
                    )

# ----------------------------------------------------------------------
# Edit / Create
# ----------------------------------------------------------------------

with tab_edit:
    NEW = "➕ New schema"
    options = [NEW] + registry.codes()

    top_l, top_r = st.columns([2, 1])
    with top_l:
        with st.container(border=True):
            target = st.selectbox(
                "Schema to edit",
                options,
                format_func=lambda v: v if v == NEW else _tr_label(v),
                key="edit_target",
            )
    with top_r:
        with st.container(border=True):
            editor_theme = st.selectbox(
                "Editor theme",
                ["monokai", "github", "solarized_dark", "solarized_light",
                 "dracula", "twilight", "chrome"],
                index=0,
                key="editor_theme",
            )
            editor_font = st.slider(
                "Font size", min_value=11, max_value=20, value=14, key="editor_font"
            )

    is_new = target == NEW
    expected_tr = None if is_new else target
    default_text = NEW_SCHEMA_TEMPLATE if is_new else read_schema_text(target)

    # Ace editor returns the current buffer on every rerun; we drive its
    # initial contents via a per-target key so switching schemas loads a
    # fresh buffer without dropping in-progress edits on the *same* target.
    ace_key = f"ace::{target}"
    editor_col, preview_col = st.columns([3, 2])

    with editor_col:
        text = st_ace(
            value=st.session_state.get(ace_key, default_text),
            language="yaml",
            theme=editor_theme,
            font_size=editor_font,
            tab_size=2,
            show_gutter=True,
            show_print_margin=False,
            wrap=False,
            auto_update=True,
            min_lines=28,
            max_lines=60,
            key=ace_key,
            placeholder="# YAML schema…",
        )

    validation_ok: bool = False
    preview_schema = None
    validation_msg: str
    try:
        preview_schema = parse_schema_yaml(text)
        validation_ok = True
        validation_msg = (
            f"✅ Valid · `{preview_schema.transaction_code}` · "
            f"{preview_schema.record_length:,} B · "
            f"{len(preview_schema.layout)} top-level items"
        )
    except SchemaValidationError as exc:
        validation_msg = f"❌ {exc}"
    except Exception as exc:  # noqa: BLE001
        validation_msg = f"❌ {type(exc).__name__}: {exc}"

    with preview_col:
        with st.container(border=True):
            st.markdown("#### Live preview")
            if validation_ok and preview_schema is not None:
                pc1, pc2 = st.columns(2)
                pc1.metric("TR code", preview_schema.transaction_code)
                pc2.metric("Record length", f"{preview_schema.record_length:,} B")
                st.caption(preview_schema.description)
                st.dataframe(
                    [
                        {
                            "Seq": i + 1,
                            "Kind": "array" if isinstance(item, Array) else "field",
                            "Name": item.name,
                            "KR": (
                                item.kor_name
                                if isinstance(item, Field)
                                else f"(배열) {item.name}"
                            ),
                            "Type": "Array" if isinstance(item, Array) else item.type,
                            "Len": (
                                item.total_length
                                if isinstance(item, Array)
                                else item.length
                            ),
                            "Offset": item.offset,
                        }
                        for i, item in enumerate(preview_schema.layout)
                    ],
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.caption("(Preview updates when the YAML parses cleanly.)")

    # Status banner spans full width
    if validation_ok:
        st.success(validation_msg)
    else:
        st.error(validation_msg)

    btn_save, btn_reset, btn_del, _ = st.columns([1, 1, 1, 3])

    with btn_save:
        if st.button(
            "💾 Save",
            type="primary",
            disabled=not validation_ok,
            key="edit_save",
        ):
            try:
                schema = write_schema_text(
                    text, expected_transaction_code=expected_tr
                )
            except SchemaValidationError as exc:
                st.error(f"Save failed: {exc}")
            else:
                _invalidate_registry()
                st.success(
                    f"Saved `{schema.transaction_code}.yaml`. Registry reloaded."
                )
                st.session_state.pop(ace_key, None)
                st.rerun()

    with btn_reset:
        if st.button("↺ Reset editor", key="edit_reset"):
            st.session_state.pop(ace_key, None)
            st.rerun()

    with btn_del:
        if not is_new:
            confirm_del = st.checkbox(
                f"I understand this will delete `{target}.yaml`.",
                key=f"edit_del_confirm::{target}",
            )
            if st.button(
                "🗑️ Delete",
                disabled=not confirm_del,
                key="edit_del_btn",
            ):
                deleted = delete_schema_file(target)
                if deleted:
                    _invalidate_registry()
                    st.success(f"Deleted `{target}.yaml`. Registry reloaded.")
                    st.session_state.pop(ace_key, None)
                    st.rerun()
                else:
                    st.error(f"No file at `{target}.yaml`.")
