"""Lakeflow Jobs helpers: trigger runs, poll state, read run history and QA output."""

import json
import uuid
from datetime import datetime, timezone
from itertools import islice

import pandas as pd
import streamlit as st

from core.data import workspace

TERMINAL_LIFECYCLE = {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}


def _value(enum_or_none) -> str:
    return getattr(enum_or_none, "value", None) or str(enum_or_none or "")


def _ts(ms: int | None) -> datetime | None:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc) if ms else None


def new_qa_run_id(env_key: str) -> str:
    """Custom QA run id, e.g. QA-PROD-20261002-143015-a1b2c3 (UTC timestamp + random suffix)."""
    return f"QA-{env_key.upper()}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def run_job(job_id: str, parameters: dict | None = None) -> int:
    if not job_id:
        raise RuntimeError("This job is not configured for the selected environment.")
    response = workspace().jobs.run_now(
        job_id=int(job_id),
        job_parameters=parameters or {},
        idempotency_token=f"qa-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"[:64],
    )
    return int(response.run_id)


def run_snapshot(run_id: int) -> dict:
    run = workspace().jobs.get_run(run_id=run_id)
    lifecycle = _value(getattr(run.state, "life_cycle_state", None))
    result = _value(getattr(run.state, "result_state", None))
    tasks = []
    for task in run.tasks or []:
        task_life = _value(getattr(task.state, "life_cycle_state", None))
        task_result = _value(getattr(task.state, "result_state", None))
        tasks.append({
            "task_key": task.task_key,
            "run_id": task.run_id,
            "status": task_result or task_life or "PENDING",
        })
    return {
        "run_id": run_id,
        "life_cycle_state": lifecycle,
        "result_state": result,
        "state_message": getattr(run.state, "state_message", "") or "",
        "run_page_url": run.run_page_url or "",
        "done": lifecycle in TERMINAL_LIFECYCLE,
        "tasks": tasks,
    }


def qa_output(run_id: int) -> dict:
    """The QA notebook exits with a JSON summary; read it from the task run."""
    client = workspace()
    run = client.jobs.get_run(run_id=run_id)
    tasks = run.tasks or []
    task = next((t for t in tasks if t.task_key == "qa_validation"), tasks[0] if tasks else None)
    output = client.jobs.get_run_output(run_id=int(task.run_id) if task else run_id)
    raw = getattr(getattr(output, "notebook_output", None), "result", None)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


@st.cache_data(ttl=30, show_spinner=False)
def recent_runs(job_id: str, limit: int = 15) -> pd.DataFrame:
    if not job_id:
        return pd.DataFrame()
    rows = []
    for run in islice(workspace().jobs.list_runs(job_id=int(job_id), limit=limit), limit):
        started = _ts(run.start_time)
        ended = _ts(run.end_time)
        duration_ms = run.run_duration or run.execution_duration or (
            (run.end_time - run.start_time) if run.end_time and run.start_time else None
        )
        rows.append({
            "run_id": run.run_id,
            "status": _value(run.state.result_state) or _value(run.state.life_cycle_state),
            "started": started,
            "ended": ended,
            "duration_min": round(duration_ms / 60000, 1) if duration_ms else None,
            "trigger": _value(run.trigger),
            "url": run.run_page_url,
        })
    return pd.DataFrame(rows)


def last_run(job_id: str) -> dict | None:
    try:
        df = recent_runs(job_id, limit=1)
    except Exception:
        return None
    return None if df.empty else df.iloc[0].to_dict()
