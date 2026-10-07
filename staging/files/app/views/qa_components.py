"""QA run rendering shared by the Data Quality and Pipeline Control pages."""

import pandas as pd
import streamlit as st

from core import ui


def run_header(run: dict) -> None:
    duration = run.get("duration_seconds")
    meta = [f"Started {ui.ago(run.get('started_at'))}"]
    if duration == duration and duration is not None:
        meta.append(f"{duration:.0f}s")
    if run.get("triggered_by"):
        meta.append(f"by {run['triggered_by']}")
    if run.get("job_run_id"):
        meta.append(f"job run {run['job_run_id']}")
    st.markdown(
        f"{ui.badge(run.get('status'))} &nbsp;{ui.run_id(run['qa_run_id'])} "
        f"&nbsp;<span class='rl-muted'>{ui.esc(' · '.join(meta))}</span>",
        unsafe_allow_html=True,
    )


def run_kpis(run: dict) -> None:
    total = int(run.get("total_tests") or 0)
    cols = st.columns(4)
    with cols[0]:
        ui.kpi("Pass rate", f"{float(run.get('pass_rate_percent') or 0):.0f}%", f"{total} tests", "◎")
    with cols[1]:
        ui.kpi("Passed", str(int(run.get("passed") or 0)), "Meeting expectations", "✔")
    with cols[2]:
        ui.kpi("Warnings", str(int(run.get("warnings") or 0)), "Review — not blocking", "▲")
    with cols[3]:
        ui.kpi("Failed", str(int(run.get("failed") or 0)), "Needs attention", "✖")


def test_table(tests: pd.DataFrame, key: str) -> None:
    f1, f2, f3 = st.columns([2, 2, 3])
    layers = f1.multiselect("Layer", sorted(tests["layer"].dropna().unique()), placeholder="All layers",
                            key=f"{key}_layers")
    statuses = f2.multiselect("Status", ["FAIL", "WARN", "PASS"], placeholder="All statuses",
                              key=f"{key}_statuses")
    search = f3.text_input("Search tests", placeholder="e.g. uniqueness, customers, SCD2", key=f"{key}_search")

    view = tests
    if layers:
        view = view[view["layer"].isin(layers)]
    if statuses:
        view = view[view["status"].isin(statuses)]
    if search:
        view = view[view["test_name"].str.contains(search, case=False, na=False)]

    st.caption(f"Showing {len(view)} of {len(tests)} tests")
    st.dataframe(
        view.fillna("").replace({"null": ""}).assign(status=view["status"].map(ui.status_label))[
            ["status", "layer", "test_name", "actual", "expected", "details"]
        ],
        hide_index=True, width="stretch", height=min(520, 38 + 35 * max(len(view), 1)),
        column_config={
            "status": st.column_config.TextColumn("Status", width="small"),
            "layer": st.column_config.TextColumn("Layer", width="small"),
            "test_name": st.column_config.TextColumn("Test", width="large"),
            "actual": "Actual", "expected": "Expected", "details": "Details",
        },
    )

    problems = tests[tests["status"] != "PASS"]
    if problems.empty:
        st.success("Every test in this run passed.", icon="✅")
        return
    has_fail = (problems["status"] == "FAIL").any()
    with st.expander(f"Investigate {len(problems)} non-passing test(s)", expanded=bool(has_fail)):
        for _, row in problems.iterrows():
            st.markdown(f"{ui.badge(row['status'])} &nbsp;**{ui.esc(row['test_name'])}** "
                        f"<span class='rl-muted'>· {ui.esc(row['layer'])}</span>", unsafe_allow_html=True)
            detail = f"Expected: {row['expected']}  ·  Actual: {row['actual']}"
            if isinstance(row.get("details"), str) and row["details"]:
                detail += f"  ·  {row['details']}"
            st.caption(detail)


def runs_for_chart(runs: pd.DataFrame, last: int = 15) -> pd.DataFrame:
    recent = runs.head(last).iloc[::-1]
    label = recent["started_at"].dt.strftime("%b %d %H:%M")
    long = pd.DataFrame({
        "run": list(label) * 3,
        "qa_run_id": list(recent["qa_run_id"]) * 3,
        "status": ["PASS"] * len(recent) + ["WARN"] * len(recent) + ["FAIL"] * len(recent),
        "tests": list(recent["passed"]) + list(recent["warnings"]) + list(recent["failed"]),
    })
    return long[long["tests"] > 0]
