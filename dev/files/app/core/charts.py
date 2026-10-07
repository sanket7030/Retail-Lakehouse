"""Altair chart helpers: thin marks, recessive axes, hover tooltips, light/dark aware."""

import altair as alt
import pandas as pd
import streamlit as st

from core import theme

# Same eight hues, stepped separately for each surface (validated palette).
SERIES_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SERIES_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
STATUS_COLORS = {"PASS": "#0ca30c", "WARN": "#fab219", "FAIL": "#d03b3b"}
MUTED = "#898781"


def is_dark() -> bool:
    return theme.is_dark()


def series(slot: int) -> str:
    return (SERIES_DARK if is_dark() else SERIES_LIGHT)[slot % 8]


def _surface() -> str:
    return theme.token("bg")


def _style(chart: alt.Chart, height: int) -> alt.Chart:
    grid = "#2c2c2a" if is_dark() else "#e6e5df"
    axis = "#3d3c38" if is_dark() else "#c3c2b7"
    return (
        chart.properties(height=height)
        .configure(background="transparent", font="IBM Plex Sans, system-ui, sans-serif")
        .configure_view(strokeWidth=0)
        .configure_axis(
            gridColor=grid, domainColor=axis, tickColor=axis,
            labelColor=MUTED, titleColor=MUTED, labelFontSize=11, titleFontSize=11,
            titleFontWeight="normal",
        )
        .configure_legend(labelColor=MUTED, titleColor=MUTED, orient="top", title=None)
    )


def show(chart: alt.Chart, height: int = 300) -> None:
    st.altair_chart(_style(chart, height), width="stretch", theme=None)


def line(df: pd.DataFrame, x: str, y: str, *, y_title: str, money: bool = True,
         height: int = 300, x_type: str = "T") -> None:
    """Single-series line with a crosshair + tooltip (bars when there are too few points for a line)."""
    if len(df) < 3:
        labelled = df.assign(period=pd.to_datetime(df[x]).dt.strftime("%b %d, %Y"))
        vbar(labelled, "period", y, value_title=y_title, money=money, height=height)
        return
    fmt = "$,.0f" if money else ",.0f"
    color = series(0)
    base = alt.Chart(df).encode(x=alt.X(f"{x}:{x_type}", title=None))
    hover = alt.selection_point(nearest=True, on="mouseover", fields=[x], empty=False)
    area = base.mark_area(opacity=0.14, color=color).encode(
        y=alt.Y(f"{y}:Q", title=y_title, axis=alt.Axis(format="$~s" if money else "~s"))
    )
    stroke = base.mark_line(strokeWidth=2, color=color).encode(y=f"{y}:Q")
    catcher = base.mark_rule(strokeWidth=12, opacity=0).encode(
        tooltip=[alt.Tooltip(f"{x}:{x_type}", title=x.replace("_", " ")), alt.Tooltip(f"{y}:Q", title=y_title, format=fmt)]
    ).add_params(hover)
    rule = base.mark_rule(color=MUTED, strokeWidth=1).encode(
        opacity=alt.condition(hover, alt.value(0.7), alt.value(0))
    )
    dot = base.mark_point(filled=True, size=70, color=color, stroke=_surface(), strokeWidth=2).encode(
        y=f"{y}:Q", opacity=alt.condition(hover, alt.value(1), alt.value(0))
    )
    show(alt.layer(area, stroke, rule, dot, catcher), height)


def hbar(df: pd.DataFrame, category: str, value: str, *, value_title: str, money: bool = True,
         height: int | None = None, slot: int = 0) -> None:
    """Ranked horizontal bars with a value tooltip."""
    fmt = "$,.0f" if money else ",.0f"
    height = height or max(160, 30 * len(df))
    chart = alt.Chart(df).mark_bar(cornerRadiusEnd=4, color=series(slot)).encode(
        y=alt.Y(f"{category}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
        x=alt.X(f"{value}:Q", title=value_title, axis=alt.Axis(format="~s")),
        tooltip=[alt.Tooltip(f"{category}:N", title=category.replace("_", " ")),
                 alt.Tooltip(f"{value}:Q", title=value_title, format=fmt)],
    )
    show(chart, height)


def vbar(df: pd.DataFrame, category: str, value: str, *, value_title: str, money: bool = True,
         height: int = 280, slot: int = 0) -> None:
    fmt = "$,.0f" if money else ",.0f"
    bar_size = min(56, max(12, 520 // max(len(df), 1)))
    chart = alt.Chart(df).mark_bar(cornerRadiusEnd=4, color=series(slot), size=bar_size).encode(
        x=alt.X(f"{category}:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y(f"{value}:Q", title=value_title, axis=alt.Axis(format="~s")),
        tooltip=[alt.Tooltip(f"{category}:N"), alt.Tooltip(f"{value}:Q", title=value_title, format=fmt)],
    )
    show(chart, height)


def status_stack(df: pd.DataFrame, x: str, *, height: int = 280) -> None:
    """Stacked PASS/WARN/FAIL counts per run (status colors, labeled legend)."""
    order = ["PASS", "WARN", "FAIL"]
    runs = df[x].nunique() or 1
    chart = alt.Chart(df).mark_bar(stroke=_surface(), strokeWidth=1, size=min(36, max(10, 320 // runs))).encode(
        x=alt.X(f"{x}:O", title=None, axis=alt.Axis(labelAngle=-35)),
        y=alt.Y("tests:Q", title="Tests", stack="zero"),
        color=alt.Color("status:N", scale=alt.Scale(domain=order, range=[STATUS_COLORS[s] for s in order]),
                        legend=alt.Legend(title=None)),
        order=alt.Order("status_rank:Q"),
        tooltip=[alt.Tooltip(f"{x}:O", title="Run"), "status:N", "tests:Q"],
    ).transform_calculate(status_rank="indexof(['PASS','WARN','FAIL'], datum.status)")
    show(chart, height)


def rate_vs_threshold(df: pd.DataFrame, category: str, rate: str, threshold: str, *,
                      title: str, height: int | None = None) -> None:
    """Bars for a failure rate with a tick showing each dataset's alert threshold."""
    height = height or max(160, 34 * len(df))
    base = alt.Chart(df).encode(y=alt.Y(f"{category}:N", title=None, sort="-x"))
    tooltip = [alt.Tooltip(f"{category}:N"), alt.Tooltip(f"{rate}:Q", title=title, format=".2f"),
               alt.Tooltip(f"{threshold}:Q", title="Threshold %", format=".2f")]
    bars = base.mark_bar(cornerRadiusEnd=4, color=series(1)).encode(
        x=alt.X(f"{rate}:Q", title=title), tooltip=tooltip
    )
    ticks = base.mark_tick(color=MUTED, thickness=2, size=22).encode(x=f"{threshold}:Q", tooltip=tooltip)
    show(alt.layer(bars, ticks), height)
