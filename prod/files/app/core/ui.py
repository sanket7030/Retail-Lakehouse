"""Shared building blocks. All colors come from theme tokens, so everything follows light/dark."""

import html
from datetime import datetime, timezone

import streamlit as st

from core import theme

STATUS_STYLE = {
    # status -> (icon, css class)
    "PASS": ("✔", "good"), "SUCCESS": ("✔", "good"), "OK": ("✔", "good"),
    "WARN": ("▲", "warning"), "ALERT": ("▲", "warning"), "WARNING": ("▲", "warning"),
    "FAIL": ("✖", "critical"), "FAILED": ("✖", "critical"), "TIMEDOUT": ("✖", "critical"),
    "INTERNAL_ERROR": ("✖", "critical"), "UPSTREAM_FAILED": ("✖", "critical"),
    "CANCELED": ("■", "neutral"), "UPSTREAM_CANCELED": ("■", "neutral"),
    "SKIPPED": ("■", "neutral"), "EXCLUDED": ("■", "neutral"),
    "RUNNING": ("●", "info"), "PENDING": ("○", "info"), "QUEUED": ("○", "info"),
    "BLOCKED": ("○", "info"), "TERMINATING": ("●", "info"),
}


def inject_css() -> None:
    theme.inject()


def esc(value) -> str:
    return html.escape(str(value))


def hero(title: str, subtitle: str, chips: list[str] | None = None, overline: str = "") -> None:
    """Page header. Chips written as 'Label · value' render the value in bold."""
    tags = []
    for chip in chips or []:
        label, _, value = chip.partition(" · ")
        tags.append(f'<span class="rl-tag">{esc(label)} <b>{esc(value)}</b></span>' if value
                    else f'<span class="rl-tag">{esc(chip)}</span>')
    over = f'<div class="rl-overline">{esc(overline)}</div>' if overline else ""
    st.markdown(
        f'<div class="rl-header">{over}<h1>{esc(title)}</h1><p>{esc(subtitle)}</p>'
        f'<div class="rl-tags">{"".join(tags)}</div></div>',
        unsafe_allow_html=True,
    )


def section(title: str, caption: str = "") -> None:
    st.markdown(
        f'<div class="rl-section"><h3>{esc(title)}</h3><span>{esc(caption)}</span></div>',
        unsafe_allow_html=True,
    )


def badge(status: str | None) -> str:
    status = (status or "UNKNOWN").upper()
    icon, cls = STATUS_STYLE.get(status, ("?", "neutral"))
    return f'<span class="rl-badge {cls}">{icon} {esc(status)}</span>'


def status_label(status: str | None) -> str:
    """Plain-text status with icon, for dataframes."""
    status = (status or "UNKNOWN").upper()
    return f"{STATUS_STYLE.get(status, ('?', ''))[0]} {status}"


def run_id(value: str) -> str:
    return f'<span class="rl-run-id">{esc(value)}</span>'


def kpi(label: str, value: str, sub: str = "", icon: str = "", value_html: bool = False) -> None:
    """KPI tile. Pass value_html=True when `value` is trusted markup such as badge()."""
    value_markup = value if value_html else esc(value)
    st.markdown(
        f'<div class="rl-card"><div class="rl-kpi-label"><span>{esc(label)}</span>'
        f'<span class="rl-kpi-icon">{esc(icon)}</span></div>'
        f'<div class="rl-kpi-value">{value_markup}</div>'
        f'<div class="rl-kpi-sub">{esc(sub)}</div></div>',
        unsafe_allow_html=True,
    )


def empty(message: str, hint: str = "") -> None:
    st.markdown(
        f'<div class="rl-empty"><div>{esc(message)}</div>'
        f'<div class="rl-muted">{esc(hint)}</div></div>',
        unsafe_allow_html=True,
    )


def query_error(error: str, what: str = "this view") -> None:
    from core.data import is_permission_error  # local import avoids a cycle

    if is_permission_error(error or ""):
        st.warning(
            f"Couldn't load {what}: the app's service principal can't read this data yet. "
            "Run `scripts/grant_app_access.sql` (read-only grants) and refresh.",
            icon="🔒",
        )
    else:
        st.warning(f"Couldn't load {what}. {(error or '')[:300]}", icon="⚠️")


def money(value) -> str:
    if value is None or value != value:  # None or NaN
        return "—"
    value = float(value)
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= limit:
            return f"${value / limit:,.2f}{suffix}"
    return f"${value:,.2f}"


def number(value) -> str:
    if value is None or value != value:
        return "—"
    value = float(value)
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= limit:
            return f"{value / limit:,.1f}{suffix}"
    return f"{value:,.0f}"


def ago(ts) -> str:
    if ts is None or ts != ts:
        return "never"
    if getattr(ts, "tzinfo", None) is None:
        ts = ts.replace(tzinfo=timezone.utc)
    seconds = (datetime.now(timezone.utc) - ts).total_seconds()
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{int(seconds // size)}{unit} ago"
    return "just now"
