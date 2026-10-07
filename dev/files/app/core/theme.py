"""Design tokens + light/dark theming.

Direction: functionalist ("less, but better") — neutral warm surfaces, a single blue accent,
status colors reserved for state, IBM Plex type, hairline borders, no decorative gradients.

Streamlit has no API to switch its theme per viewer, so the native theme (.streamlit/config.toml)
is the LIGHT palette and dark mode is applied per session by this module: the same tokens are
re-defined for dark and Streamlit's own widgets are restyled against them.
"""

import streamlit as st

TOKENS = {
    "light": {
        "bg": "#f6f6f3", "surface": "#ffffff", "surface-2": "#efeeea", "border": "#dddcd5",
        "text": "#141413", "text-2": "#4a4945", "muted": "#7d7c76",
        "accent": "#2a78d6", "accent-text": "#1c5cab", "accent-soft": "rgba(42,120,214,.10)",
        "good": "#0b8a0b", "good-soft": "rgba(12,163,12,.10)",
        "warning": "#a86f00", "warning-soft": "rgba(250,178,25,.16)",
        "critical": "#c43333", "critical-soft": "rgba(208,59,59,.10)",
        "neutral": "#6f6e69", "neutral-soft": "rgba(137,135,129,.14)",
        "shadow": "0 1px 2px rgba(20,20,19,.05)",
    },
    "dark": {
        # Warm neutral darks (not an inversion); off-white text for comfort.
        "bg": "#141413", "surface": "#1c1c1a", "surface-2": "#252523", "border": "#34332f",
        "text": "#ecebe5", "text-2": "#bdbcb4", "muted": "#8d8c85",
        "accent": "#4a90e8", "accent-text": "#86b6ef", "accent-soft": "rgba(74,144,232,.16)",
        "good": "#3cc23c", "good-soft": "rgba(60,194,60,.14)",
        "warning": "#f0b429", "warning-soft": "rgba(240,180,41,.14)",
        "critical": "#ef6b6b", "critical-soft": "rgba(239,107,107,.14)",
        "neutral": "#a3a29b", "neutral-soft": "rgba(163,162,155,.14)",
        "shadow": "0 1px 2px rgba(0,0,0,.4)",
    },
}

_SESSION_KEY = "dark_mode"


def is_dark() -> bool:
    return bool(st.session_state.get(_SESSION_KEY, False))


def init_from_url() -> None:
    """Restore the viewer's choice from ?theme=dark so it survives refreshes and shared links."""
    if _SESSION_KEY not in st.session_state:
        st.session_state[_SESSION_KEY] = st.query_params.get("theme") == "dark"


def _sync_url() -> None:
    if st.session_state.get(_SESSION_KEY):
        st.query_params["theme"] = "dark"
    elif "theme" in st.query_params:
        del st.query_params["theme"]


def toggle(container=st.sidebar) -> None:
    container.toggle(":material/dark_mode: Dark mode", key=_SESSION_KEY, on_change=_sync_url)


def token(name: str) -> str:
    return TOKENS["dark" if is_dark() else "light"][name]


def _vars(mode: str) -> str:
    return "".join(f"--rl-{k}:{v};" for k, v in TOKENS[mode].items())


# Components we render ourselves — written once against the tokens.
_COMPONENT_CSS = """
.block-container { padding-top: 2rem; padding-bottom: 4rem; max-width: 1360px; }
button:not([role="switch"]), [data-baseweb="select"] > div { min-height: 2.5rem; }

/* Toggle (st.toggle): switch and label on one centred line */
[data-testid="stCheckbox"] label { display: flex !important; align-items: center !important;
  min-height: 2.5rem; gap: .6rem; }
[data-testid="stCheckbox"] label > div { margin-top: 0 !important; margin-bottom: 0 !important;
  align-self: center !important; }
[data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] p { margin: 0 !important; line-height: 1.25; }
/* Off state needs a visible track (≥3:1 non-text contrast) */
[data-testid="stCheckbox"]:not([data-selected="true"]) label > span + div {
  box-shadow: inset 0 0 0 1.5px var(--rl-muted); }
.rl-num { font-variant-numeric: tabular-nums; }

/* Page header — overline, title, one-line purpose, metadata tags, hairline rule */
.rl-header { padding: .25rem 0 1.1rem 0; margin-bottom: 1.4rem; border-bottom: 1px solid var(--rl-border); }
.rl-overline { font-size: .72rem; font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
               color: var(--rl-accent-text); margin-bottom: .45rem; }
.rl-header h1 { font-size: 1.85rem; line-height: 1.15; font-weight: 600; letter-spacing: -.01em;
                margin: 0 0 .35rem 0; padding: 0; color: var(--rl-text); }
.rl-header p { margin: 0; color: var(--rl-text-2); font-size: 1rem; max-width: 72ch; }
.rl-tags { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .85rem; }
.rl-tag { font-size: .78rem; color: var(--rl-text-2); border: 1px solid var(--rl-border); border-radius: 6px;
          padding: .15rem .55rem; background: var(--rl-surface); font-variant-numeric: tabular-nums; }
.rl-tag b { color: var(--rl-text); font-weight: 600; }

/* KPI tiles */
.rl-card { background: var(--rl-surface); border: 1px solid var(--rl-border); border-radius: 10px;
           padding: 1rem 1.1rem; height: 100%; box-shadow: var(--rl-shadow); }
.rl-kpi-label { font-size: .72rem; font-weight: 600; text-transform: uppercase; letter-spacing: .08em;
                color: var(--rl-muted); margin-bottom: .5rem; display: flex; justify-content: space-between; }
.rl-kpi-value { font-size: 1.65rem; font-weight: 600; line-height: 1.15; color: var(--rl-text);
                font-variant-numeric: tabular-nums; letter-spacing: -.01em; }
.rl-kpi-sub { font-size: .84rem; color: var(--rl-text-2); margin-top: .4rem; }
.rl-kpi-icon { font-size: 1rem; opacity: .9; }

/* Section heading */
.rl-section { display: flex; align-items: baseline; flex-wrap: wrap; gap: .25rem .75rem; margin: 2rem 0 .75rem 0; }
.rl-section h3 { margin: 0; padding: 0; font-size: 1.12rem; font-weight: 600; color: var(--rl-text); }
.rl-section span { color: var(--rl-muted); font-size: .88rem; }

/* Status badges: icon + label, never color alone */
.rl-badge { display: inline-flex; align-items: center; gap: .3rem; padding: .1rem .55rem; border-radius: 6px;
            font-size: .78rem; font-weight: 600; white-space: nowrap; border: 1px solid currentColor;
            font-variant-numeric: tabular-nums; }
.rl-badge.good { color: var(--rl-good) !important; background: var(--rl-good-soft); }
.rl-badge.warning { color: var(--rl-warning) !important; background: var(--rl-warning-soft); }
.rl-badge.critical { color: var(--rl-critical) !important; background: var(--rl-critical-soft); }
.rl-badge.info { color: var(--rl-accent-text) !important; background: var(--rl-accent-soft); }
.rl-badge.neutral { color: var(--rl-neutral) !important; background: var(--rl-neutral-soft); }

/* Live task board */
.rl-flow { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: .5rem; }
.rl-task { border: 1px solid var(--rl-border); border-radius: 8px; padding: .55rem .7rem;
           background: var(--rl-surface); font-size: .85rem; color: var(--rl-text); }
.rl-task b { display: block; margin-bottom: .3rem; font-weight: 600; font-size: .82rem; }

/* Empty state + misc */
.rl-empty { text-align: center; padding: 1.75rem 1rem; color: var(--rl-text-2);
            border: 1px dashed var(--rl-border); border-radius: 10px; background: var(--rl-surface); }
.rl-empty .rl-muted { margin-top: .25rem; }
.rl-muted { color: var(--rl-muted) !important; font-size: .85rem; }
.rl-run-id { font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: .82rem; color: var(--rl-text);
             background: var(--rl-surface-2); border: 1px solid var(--rl-border); border-radius: 6px;
             padding: .1rem .45rem; }

/* Sidebar brand */
.rl-brand { display: flex; align-items: center; gap: .65rem; margin: .25rem 0 1rem 0; }
.rl-brand-mark { width: 34px; height: 34px; border-radius: 8px; background: var(--rl-accent); color: #fff;
                 display: grid; place-items: center; font-weight: 700; font-size: .85rem; letter-spacing: .02em; }
.rl-brand-name { font-weight: 600; color: var(--rl-text); line-height: 1.15; }
.rl-brand-sub { font-size: .76rem; color: var(--rl-muted); }

@media (max-width: 640px) {
  .rl-header h1 { font-size: 1.5rem; }
  .rl-kpi-value { font-size: 1.4rem; }
}
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
"""

# Streamlit's own widgets, restyled for dark mode against the same tokens.
_DARK_OVERRIDES = """
:root { color-scheme: dark; }
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"],
[data-testid="stBottom"], [data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"] {
  background: var(--rl-bg) !important; color: var(--rl-text) !important; }
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"], [data-testid="stSidebar"] > div { background: var(--rl-surface-2) !important; }
[data-testid="stSidebar"] { border-right: 1px solid var(--rl-border); }

.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6, .stApp p, .stApp li, .stApp label,
.stApp strong, .stApp em, .stApp td, .stApp th, [data-testid="stMarkdownContainer"],
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p, [data-testid="stMetricValue"],
[data-testid="stMetricLabel"], [data-testid="stSidebarNavLink"] span, [data-testid="stNavSectionHeader"],
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary p { color: var(--rl-text) !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p, .stApp small { color: var(--rl-muted) !important; }
.stApp a:not([data-testid="stSidebarNavLink"]):not([data-testid="stPageLink-NavLink"]) { color: var(--rl-accent-text) !important; }
[data-testid="stSidebarNavLink"], [data-testid="stSidebarNavLink"] * { color: var(--rl-text) !important; }
[data-testid="stSidebarNavLink"]:hover, [data-testid="stSidebarNavLink"][aria-current="page"] {
  background: var(--rl-surface) !important; }
[data-testid="stIconMaterial"] { color: var(--rl-text-2) !important; }
hr, [data-testid="stDivider"] { border-color: var(--rl-border) !important; background: var(--rl-border) !important; }

/* Inputs, selects, text areas, chat input */
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"],
.stTextInput input, .stTextArea textarea, .stNumberInput input, [data-testid="stChatInput"],
[data-testid="stChatInput"] > div, [data-testid="stChatInput"] textarea {
  background: var(--rl-surface) !important; color: var(--rl-text) !important; border-color: var(--rl-border) !important; }
[data-baseweb="select"] span, [data-baseweb="select"] div { color: var(--rl-text) !important; }
/* Select / multiselect boxes (no testid on the box itself — it wraps the tags container) */
[data-testid="stMultiSelect"] > div > div, [data-testid="stSelectbox"] > div > div,
div:has(> [data-testid="stMultiSelectTagsContainer"]) {
  background: var(--rl-surface) !important; border-color: var(--rl-border) !important; color: var(--rl-text) !important; }
[data-testid="stMultiSelect"] input, [data-testid="stSelectbox"] input,
[data-testid="stSelectbox"] div, [data-testid="stMultiSelect"] svg, [data-testid="stSelectbox"] svg {
  color: var(--rl-text) !important; }
input::placeholder, textarea::placeholder { color: var(--rl-muted) !important; opacity: 1; }
[data-baseweb="tag"] { background: var(--rl-surface-2) !important; }
[data-baseweb="tag"] span { color: var(--rl-text) !important; }
[data-baseweb="popover"] > div, [data-baseweb="popover"] ul, [data-baseweb="menu"], [role="listbox"],
[data-testid="stPopoverBody"], [role="dialog"] {
  background: var(--rl-surface) !important; color: var(--rl-text) !important; border-color: var(--rl-border) !important; }
[role="option"] { color: var(--rl-text) !important; }
[role="option"]:hover, [role="option"][aria-selected="true"] { background: var(--rl-surface-2) !important; }
[data-baseweb="tooltip"] > div, [data-baseweb="tooltip"] div { background: var(--rl-surface-2) !important; color: var(--rl-text) !important; }

/* Buttons (secondary, popover, segmented, download) */
[data-testid="stBaseButton-secondary"], [data-testid="stPopoverButton"], [data-testid="stBaseButton-minimal"],
[data-testid="stBaseButton-segmented_control"], [data-testid="stBaseButton-pills"],
[data-testid="stBaseButton-secondaryFormSubmit"], [data-testid="stDownloadButton"] button {
  background: var(--rl-surface) !important; color: var(--rl-text) !important; border-color: var(--rl-border) !important; }
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stPopoverButton"]:hover,
[data-testid="stBaseButton-segmented_control"]:hover { border-color: var(--rl-accent) !important; color: var(--rl-accent-text) !important; }
[data-testid="stBaseButton-segmented_controlActive"], [data-testid="stBaseButton-pillsActive"] {
  background: var(--rl-accent-soft) !important; color: var(--rl-accent-text) !important; border-color: var(--rl-accent) !important; }
button[data-variant="segmented_control"], button[data-variant="pills"] {
  background: var(--rl-surface) !important; color: var(--rl-text-2) !important; border-color: var(--rl-border) !important; }
button[data-variant="segmented_control"][aria-checked="true"], button[data-variant="pills"][aria-checked="true"] {
  background: var(--rl-accent-soft) !important; color: var(--rl-accent-text) !important; border-color: var(--rl-accent) !important; }
button[data-variant="segmented_control"] *, button[data-variant="pills"] * { color: inherit !important; }
[data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"], [data-testid="stTextAreaRootElement"] {
  background: var(--rl-surface) !important; border-color: var(--rl-border) !important; }
[data-testid="stElementToolbarButtonContainer"] { background: var(--rl-surface-2) !important; }
[data-testid="stElementToolbarButtonContainer"] *, [data-testid="stSidebarCollapseButton"] *,
[data-testid="stBaseButton-headerNoPadding"] { color: var(--rl-text-2) !important; }
[data-testid="stExpanderDetails"] { border-color: var(--rl-border) !important; }
button:disabled, [data-testid="stBaseButton-primary"]:disabled { opacity: .45; }
[data-testid="stBaseButton-secondary"] *, [data-testid="stPopoverButton"] * { color: inherit !important; }

/* Tabs */
[data-baseweb="tab-list"] { background: transparent !important; }
[data-baseweb="tab"] { background: transparent !important; }
[data-baseweb="tab"] p { color: var(--rl-text-2) !important; }
[data-baseweb="tab"][aria-selected="true"] p { color: var(--rl-accent-text) !important; }
[data-baseweb="tab-border"] { background: var(--rl-border) !important; }

/* Expanders, status, bordered containers, chat messages */
[data-testid="stExpander"] details, [data-testid="stExpander"] > details {
  background: var(--rl-surface) !important; border-color: var(--rl-border) !important; }
[data-testid="stExpander"] summary:hover { background: var(--rl-surface-2) !important; }
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stVerticalBlock"][height],
div[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"] { border-color: var(--rl-border) !important; }
[data-testid="stChatMessage"] { background: var(--rl-surface) !important; border: 1px solid var(--rl-border); }

/* Code */
[data-testid="stCode"] pre, [data-testid="stCode"], .stCode pre, .stApp pre, .stApp code {
  background: var(--rl-surface-2) !important; color: var(--rl-text) !important; }
.stApp pre span { color: inherit; }

/* Alerts keep their tint; text must stay readable */
[data-testid="stAlertContainer"] { background: var(--rl-surface-2) !important; border: 1px solid var(--rl-border); }
[data-testid="stAlertContainer"] p, [data-testid="stAlertContainer"] div { color: var(--rl-text) !important; }

/* Data grid is canvas-drawn from the (light) native theme: re-tone it for dark. */
[data-testid="stDataFrame"] > div, [data-testid="stDataFrameResizable"] {
  filter: invert(.92) hue-rotate(180deg) brightness(1.05); }
[data-testid="stTable"] table, [data-testid="stTable"] th, [data-testid="stTable"] td {
  background: var(--rl-surface) !important; color: var(--rl-text) !important; border-color: var(--rl-border) !important; }

/* Vega tooltip is appended to <body> */
#vg-tooltip-element { background: var(--rl-surface-2) !important; color: var(--rl-text) !important;
  border: 1px solid var(--rl-border) !important; }
#vg-tooltip-element td { color: var(--rl-text) !important; }
[data-testid="stSlider"] [data-testid="stSliderTickBarMin"], [data-testid="stSlider"] [data-testid="stSliderTickBarMax"] {
  color: var(--rl-muted) !important; }
[data-testid="stToolbar"] *, [data-testid="stMainMenu"] * { color: var(--rl-text-2) !important; }
"""


def inject() -> None:
    mode = "dark" if is_dark() else "light"
    css = f":root {{ {_vars(mode)} }}\n{_COMPONENT_CSS}"
    if mode == "dark":
        css += _DARK_OVERRIDES
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
