import time

import streamlit as st

from core import nav, ui
from core.config import Environment, current_env
from core.data import clear_cache
from core.jobs import new_qa_run_id, recent_runs, run_job, run_snapshot
from views.qa_components import run_header, run_kpis, test_table
from views.shared import qa_run_tests, qa_runs

POLL_SECONDS = 4
TIMEOUT_SECONDS = 1800
LAYER_ORDER = ("Bronze", "Silver", "Gold", "QA")


def _layer(task_key: str) -> str:
    if task_key.startswith("silver"):
        return "Silver"
    if task_key.startswith("gold"):
        return "Gold"
    if task_key.startswith("qa"):
        return "QA"
    return "Bronze"


def _render_tasks(snapshot: dict) -> str:
    groups: dict[str, list[dict]] = {}
    for task in snapshot["tasks"]:
        groups.setdefault(_layer(task["task_key"]), []).append(task)
    blocks = []
    for layer in LAYER_ORDER:
        tasks = groups.get(layer)
        if not tasks:
            continue
        cells = "".join(
            f'<div class="rl-task"><b>{ui.esc(t["task_key"])}</b>{ui.badge(t["status"])}</div>' for t in tasks
        )
        blocks.append(f'<div class="rl-muted" style="margin:.6rem 0 .3rem">{layer}</div>'
                      f'<div class="rl-flow">{cells}</div>')
    return "".join(blocks)


def _watch(run_id: int, label: str) -> dict:
    """Poll a run, rendering a live task-level progress board until it finishes."""
    header = st.empty()
    board = st.empty()
    started = time.time()
    while True:
        snapshot = run_snapshot(run_id)
        status = snapshot["result_state"] or snapshot["life_cycle_state"] or "PENDING"
        done = sum(1 for t in snapshot["tasks"] if t["status"] not in {"PENDING", "RUNNING", "QUEUED", "BLOCKED"})
        header.markdown(
            f"**{ui.esc(label)}** &nbsp;{ui.badge(status)} &nbsp;"
            f'<span class="rl-muted">{done}/{len(snapshot["tasks"])} tasks · '
            f'{int(time.time() - started)}s elapsed · job run '
            f'<a href="{snapshot["run_page_url"]}" target="_blank">{run_id}</a></span>',
            unsafe_allow_html=True,
        )
        board.markdown(_render_tasks(snapshot), unsafe_allow_html=True)
        if snapshot["done"]:
            return snapshot
        if time.time() - started > TIMEOUT_SECONDS:
            snapshot["result_state"] = "TIMEDOUT"
            return snapshot
        time.sleep(POLL_SECONDS)


def _viewer() -> str:
    try:
        return st.context.headers.get("X-Forwarded-Email") or "qa-app"
    except Exception:
        return "qa-app"


def _run_qa(env: Environment) -> dict:
    qa_run_id = new_qa_run_id(env.key)
    st.markdown(f"QA run id {ui.run_id(qa_run_id)}", unsafe_allow_html=True)
    job_run = run_job(env.qa_job, {"environment": env.param, "qa_run_id": qa_run_id,
                                   "triggered_by": _viewer()})
    snapshot = _watch(job_run, f"{env.key} QA suite")
    snapshot["qa_run_id"] = qa_run_id
    return snapshot


def _store(env: Environment, result: dict) -> None:
    st.session_state.setdefault("pipeline_results", {})[env.key] = result
    if result.get("qa", {}).get("qa_run_id"):
        # Data Quality opens on this run.
        st.session_state[f"qa_selected_{env.key}"] = result["qa"]["qa_run_id"]
    clear_cache()
    recent_runs.clear()


def _action_panel(env: Environment) -> None:
    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(border=True):
            st.markdown("#### End-to-end + QA")
            st.caption("Runs Bronze → Silver → Gold for all 6 datasets, then the QA suite if the pipeline succeeds.")
            run_e2e = st.button("Run full pipeline", type="primary", width="stretch", icon=":material/play_arrow:",
                                disabled=not (env.e2e_job and env.qa_job), key="btn_e2e")
    with right:
        with st.container(border=True):
            st.markdown("#### QA suite only")
            st.caption("Validates existing tables: schemas, uniqueness, SCD2 integrity, DQ status and "
                       "reconciliation. Results are stored with a unique run id.")
            run_only_qa = st.button("Run QA suite", width="stretch", icon=":material/fact_check:",
                                    disabled=not env.qa_job, key="btn_qa")

    if not env.e2e_job or not env.qa_job:
        st.info(f"Some jobs aren't configured for {env.key}. Check the app's job resources.", icon="ℹ️")

    if run_e2e:
        with st.status(f"Running {env.key} end-to-end pipeline…", expanded=True) as status:
            try:
                e2e = _watch(run_job(env.e2e_job, {"environment": env.param}), f"{env.key} E2E pipeline")
                if e2e["result_state"] != "SUCCESS":
                    status.update(label="E2E pipeline failed — QA was not started", state="error")
                    _store(env, {"e2e": e2e})
                else:
                    st.write("Pipeline succeeded. Starting QA suite…")
                    qa = _run_qa(env)
                    ok = qa["result_state"] == "SUCCESS"
                    status.update(label=f"E2E + QA completed · {qa['qa_run_id']}" if ok
                                  else "E2E succeeded but QA failed", state="complete" if ok else "error")
                    _store(env, {"e2e": e2e, "qa": qa})
            except Exception as exc:
                status.update(label="Couldn't start the run", state="error")
                st.error(str(exc))

    if run_only_qa:
        with st.status(f"Running {env.key} QA suite…", expanded=True) as status:
            try:
                qa = _run_qa(env)
                ok = qa["result_state"] == "SUCCESS"
                status.update(label=f"QA suite completed · {qa['qa_run_id']}" if ok else "QA suite failed",
                              state="complete" if ok else "error")
                _store(env, {"qa": qa})
            except Exception as exc:
                status.update(label="Couldn't start the QA run", state="error")
                st.error(str(exc))


def _qa_results(env: Environment) -> None:
    result = st.session_state.get("pipeline_results", {}).get(env.key, {})
    just_ran = result.get("qa", {}).get("qa_run_id")

    runs, error = qa_runs(env, limit=30)
    if runs is None or runs.empty:
        ui.section("QA results")
        if error:
            ui.query_error(error, "QA results")
        else:
            ui.empty("No QA results yet.", "Run the QA suite above to validate this environment.")
        return

    match = runs[runs["qa_run_id"] == just_ran] if just_ran else runs.head(0)
    run = (match if not match.empty else runs).iloc[0].to_dict()
    source = "the run you just triggered" if not match.empty else f"latest stored run · {ui.ago(run['started_at'])}"
    ui.section("QA results", source)
    if just_ran and match.empty:
        st.info(f"Run {just_ran} hasn't been stored yet (the job may have failed before persisting). "
                "Showing the latest stored run instead.", icon="ℹ️")

    run_header(run)
    st.write("")
    run_kpis(run)
    st.write("")
    tests, error = qa_run_tests(env, run["qa_run_id"])
    if tests is None or tests.empty:
        ui.query_error(error or "No test rows found.", "the run's test results")
    else:
        test_table(tests, key=f"pipe_{env.key}")
    st.page_link(nav.page("quality"), label="Open QA history in Data Quality", icon=":material/arrow_forward:")


def _history(env: Environment) -> None:
    ui.section("Job run history", "Most recent Databricks job runs")
    tabs = st.tabs(["End-to-end pipeline", "QA suite"])
    for tab, job_id in zip(tabs, (env.e2e_job, env.qa_job)):
        with tab:
            if not job_id:
                ui.empty("Job not configured for this environment.")
                continue
            try:
                runs = recent_runs(job_id)
            except Exception as exc:
                ui.query_error(str(exc), "run history")
                continue
            if runs.empty:
                ui.empty("No runs yet.")
                continue
            ok = (runs["status"] == "SUCCESS").mean() * 100
            st.caption(f"Success rate over the last {len(runs)} runs: **{ok:.0f}%**")
            st.dataframe(
                runs.assign(status=runs["status"].map(ui.status_label)),
                hide_index=True, width="stretch",
                column_config={
                    "run_id": st.column_config.NumberColumn("Job run", format="%d"),
                    "status": "Status",
                    "started": st.column_config.DatetimeColumn("Started (UTC)", format="YYYY-MM-DD HH:mm"),
                    "ended": st.column_config.DatetimeColumn("Ended (UTC)", format="YYYY-MM-DD HH:mm"),
                    "duration_min": st.column_config.NumberColumn("Duration (min)", format="%.1f"),
                    "trigger": "Trigger",
                    "url": st.column_config.LinkColumn("Open", display_text="View run ↗"),
                },
            )


def render() -> None:
    env = current_env()
    ui.hero(
        "Pipeline Control",
        "Trigger the medallion pipeline and QA suite, watch every task live, and review the stored results.",
        [f"Environment · {env.key}", f"E2E job · {env.e2e_job or 'n/a'}", f"QA job · {env.qa_job or 'n/a'}"],
        overline="Operate",
    )
    _action_panel(env)

    result = st.session_state.get("pipeline_results", {}).get(env.key, {})
    if "e2e" in result and result["e2e"].get("result_state") != "SUCCESS":
        e2e = result["e2e"]
        st.error(f"Last E2E run {e2e['run_id']} ended {e2e['result_state'] or e2e['life_cycle_state']}. "
                 f"{e2e.get('state_message', '')}", icon="🚨")

    _qa_results(env)
    _history(env)
