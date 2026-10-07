"""Page registry so views can link to each other (st.page_link needs the StreamlitPage object)."""

import streamlit as st

_PAGES: dict[str, st.Page] = {}


def register(key: str, page: st.Page) -> st.Page:
    _PAGES[key] = page
    return page


def page(key: str) -> st.Page:
    return _PAGES[key]
