from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="GlobalMart Lakehouse",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from core import nav, theme, ui  # noqa: E402  (set_page_config must run first)
from core.config import DEFAULT_ENVIRONMENT, ENVIRONMENTS, LLM_ENDPOINT, WAREHOUSE_ID  # noqa: E402
from core.data import clear_cache, list_catalogs  # noqa: E402
from views import assistant, explorer, insights, overview, pipeline, quality  # noqa: E402

theme.init_from_url()

if "env" not in st.session_state:
    st.session_state["env"] = DEFAULT_ENVIRONMENT if DEFAULT_ENVIRONMENT in ENVIRONMENTS else "PROD"

ASSETS = Path(__file__).parent / "assets"
st.logo(str(ASSETS / ("logo_dark.svg" if theme.is_dark() else "logo_light.svg")),
        icon_image=str(ASSETS / "logo_icon.svg"), size="large")

with st.sidebar:
    picked = st.segmented_control("Environment", list(ENVIRONMENTS), default=st.session_state["env"],
                                  key="env_picker")
    if picked:  # the control can be deselected; keep the last choice then
        st.session_state["env"] = picked
    env = ENVIRONMENTS[st.session_state["env"]]
    st.caption(f"Catalog `{env.catalog}`")
    theme.toggle(st)

# Inject after the toggle so the chosen theme applies on this very run.
ui.inject_css()

navigation = st.navigation(
    {
        "Operate": [
            nav.register("overview", st.Page(overview.render, title="Command Center",
                                             icon=":material/space_dashboard:", url_path="overview", default=True)),
            nav.register("pipeline", st.Page(pipeline.render, title="Pipeline Control",
                                             icon=":material/play_circle:", url_path="pipeline")),
            nav.register("quality", st.Page(quality.render, title="Data Quality",
                                            icon=":material/verified:", url_path="quality")),
        ],
        "Analyze": [
            nav.register("insights", st.Page(insights.render, title="Business Insights",
                                             icon=":material/insights:", url_path="insights")),
            nav.register("explorer", st.Page(explorer.render, title="Data Explorer",
                                             icon=":material/table_view:", url_path="explorer")),
            nav.register("ask", st.Page(assistant.render, title="Ask AI",
                                        icon=":material/auto_awesome:", url_path="ask")),
        ],
    }
)

with st.sidebar:
    st.divider()
    if st.button("Refresh data", icon=":material/refresh:", width="stretch"):
        clear_cache()
        st.rerun()
    with st.expander("Connections"):
        st.markdown(
            f"{'🟢' if WAREHOUSE_ID else '🔴'} SQL warehouse `{WAREHOUSE_ID or 'not configured'}`  \n"
            f"{'🟢' if env.e2e_job else '🔴'} E2E job `{env.e2e_job or 'n/a'}`  \n"
            f"{'🟢' if env.qa_job else '🔴'} QA job `{env.qa_job or 'n/a'}`  \n"
            f"✨ Model `{LLM_ENDPOINT}`  \n"
            f"📚 {len(list_catalogs())} catalogs readable"
        )
    st.caption("Data is cached for 5 minutes.")

navigation.run()
