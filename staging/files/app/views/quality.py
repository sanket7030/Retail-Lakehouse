import streamlit as st

from core import charts, ui
from core.config import DATASETS, current_env
from core.data import has_table, try_query
from views.qa_components import run_header, run_kpis, runs_for_chart, test_table
from views.shared import latest_dq, qa_run_tests, qa_runs


def _qa_runs(env) -> None:
    ui.section("QA runs", "Every QA run is stored in monitoring.qa_run_summary (one row per run) "
                          "and monitoring.qa_test_results (one row per test)")
    runs, error = qa_runs(env)
    if runs is None:
        if error:
            ui.query_error(error, "QA runs")
        else:
            ui.empty("No QA runs yet for this environment.",
                     "Run the QA suite from Pipeline Control — results will appear here.")
        return
    if runs.empty:
        ui.empty("No QA runs recorded for this environment.")
        return

    # Which run to show: one picked in the table, else one just triggered from Pipeline Control, else latest.
    run_ids = list(runs["qa_run_id"])
    selected = st.session_state.get(f"qa_selected_{env.key}")
    if selected not in run_ids:
        selected = run_ids[0]

    left, right = st.columns([2, 3], gap="large")
    with left:
        st.markdown("<span class='rl-muted'>Outcomes of the last 15 runs</span>", unsafe_allow_html=True)
        charts.status_stack(runs_for_chart(runs), "run", height=260)
    with right:
        st.markdown("<span class='rl-muted'>Run history — click a row to open it</span>", unsafe_allow_html=True)
        table = runs.assign(status=runs["status"].map(ui.status_label))[
            ["qa_run_id", "status", "pass_rate_percent", "failed", "warnings", "started_at", "triggered_by"]
        ]
        event = st.dataframe(
            table, hide_index=True, width="stretch", height=260,
            on_select="rerun", selection_mode="single-row", key=f"qa_runs_table_{env.key}",
            column_config={
                "qa_run_id": st.column_config.TextColumn("Run ID", width="large"),
                "status": st.column_config.TextColumn("Status", width="small"),
                "pass_rate_percent": st.column_config.NumberColumn("Pass %", format="%.0f%%"),
                "failed": st.column_config.NumberColumn("Fail", format="%d"),
                "warnings": st.column_config.NumberColumn("Warn", format="%d"),
                "started_at": st.column_config.DatetimeColumn("Started (UTC)", format="MMM DD HH:mm"),
                "triggered_by": "Triggered by",
            },
        )
    rows = getattr(getattr(event, "selection", None), "rows", None) or []
    if rows:
        selected = run_ids[rows[0]]
        st.session_state[f"qa_selected_{env.key}"] = selected

    run = runs[runs["qa_run_id"] == selected].iloc[0].to_dict()
    ui.section("Run detail", "Latest run unless you pick another one above")
    run_header(run)
    st.write("")
    run_kpis(run)
    st.write("")
    tests, error = qa_run_tests(env, selected)
    if tests is None:
        ui.query_error(error or "No test rows found.", "the run's test results")
    elif tests.empty:
        ui.empty("No test rows stored for this run.")
    else:
        test_table(tests, key=f"dq_{env.key}")


def _silver_dq(env) -> None:
    ui.section("Silver data quality", "Latest batch per dataset · bar = failure rate, tick = alert threshold")
    dq, error = latest_dq(env)
    if dq is None:
        if error:
            ui.query_error(error, "DQ metrics")
        else:
            ui.empty("No DQ metrics yet.")
        return
    left, right = st.columns([2, 3], gap="large")
    with left:
        charts.rate_vs_threshold(dq, "dataset", "dq_failure_rate_percent", "dq_failure_threshold_percent",
                                 title="Failure rate %")
    with right:
        st.dataframe(
            dq.assign(dq_status=dq["dq_status"].map(ui.status_label)),
            hide_index=True, width="stretch",
            column_order=["dataset", "dq_status", "total_records", "valid_records", "quarantined_records",
                          "dq_failure_rate_percent", "recorded_at"],
            column_config={
                "dataset": "Dataset", "dq_status": "Status",
                "total_records": st.column_config.NumberColumn("Records", format="%d"),
                "valid_records": st.column_config.NumberColumn("Valid", format="%d"),
                "quarantined_records": st.column_config.NumberColumn("Quarantined", format="%d"),
                "dq_failure_rate_percent": st.column_config.NumberColumn("Failure %", format="%.2f"),
                "recorded_at": st.column_config.DatetimeColumn("Recorded", format="MMM DD HH:mm"),
            },
        )


def _bronze_ingestion(env) -> None:
    c = env.catalog
    ui.section("Bronze ingestion health", "Rescued / corrupt records in the latest batch")
    if not has_table(c, "monitoring.bronze_ingestion_metrics"):
        ui.empty("No ingestion metrics yet.")
        return
    df, error = try_query(f"""
        SELECT dataset, ingestion_status, total_records, rescued_records, corrupt_records,
               rescued_rate_percent, corrupt_rate_percent, recorded_at
        FROM (SELECT *, row_number() OVER (PARTITION BY dataset ORDER BY recorded_at DESC) rn
              FROM `{c}`.monitoring.bronze_ingestion_metrics) WHERE rn = 1 ORDER BY dataset
    """)
    if df is None:
        ui.query_error(error, "ingestion metrics")
        return
    st.dataframe(
        df.assign(ingestion_status=df["ingestion_status"].map(ui.status_label)),
        hide_index=True, width="stretch",
        column_config={
            "dataset": "Dataset", "ingestion_status": "Status",
            "total_records": st.column_config.NumberColumn("Records", format="%d"),
            "rescued_records": st.column_config.NumberColumn("Rescued", format="%d"),
            "corrupt_records": st.column_config.NumberColumn("Corrupt", format="%d"),
            "rescued_rate_percent": st.column_config.NumberColumn("Rescued %", format="%.2f"),
            "corrupt_rate_percent": st.column_config.NumberColumn("Corrupt %", format="%.2f"),
            "recorded_at": st.column_config.DatetimeColumn("Recorded", format="MMM DD HH:mm"),
        },
    )


def _quarantine(env) -> None:
    c = env.catalog
    ui.section("Quarantine explorer", "Why records were rejected in Silver")
    available = [ds for ds in DATASETS if has_table(c, f"silver_quarantine.{ds}")]
    if not available:
        ui.empty("No quarantine tables yet — nothing has been rejected.")
        return
    dataset = st.segmented_control("Dataset", available, default=available[0], key="q_dataset")
    if not dataset:
        return
    table = f"`{c}`.silver_quarantine.{dataset}"
    reasons, error = try_query(f"""
        SELECT trim(reason) AS reason, COUNT(*) AS records
        FROM (SELECT explode(split(_quality_reason, ';')) AS reason FROM {table})
        WHERE trim(reason) <> '' GROUP BY trim(reason) ORDER BY records DESC LIMIT 15
    """)
    left, right = st.columns([2, 3], gap="large")
    with left:
        if reasons is None:
            ui.query_error(error, "quarantine reasons")
        elif reasons.empty:
            ui.empty(f"No quarantined {dataset} records. 🎉")
        else:
            charts.hbar(reasons, "reason", "records", value_title="Records", money=False, slot=1)
    with right:
        sample, error = try_query(f"SELECT * FROM {table} LIMIT 200")
        if sample is None:
            ui.query_error(error, "quarantined rows")
        elif not sample.empty:
            first = [col for col in ("_quality_reason", "_quality_status") if col in sample.columns]
            st.dataframe(sample[first + [c_ for c_ in sample.columns if c_ not in first]],
                         hide_index=True, width="stretch", height=360)
            st.caption(f"Showing up to 200 rows from `{c}.silver_quarantine.{dataset}`. "
                       "Fix at source and rerun, or use the DQ reprocessing job to re-validate a batch.")


def _job_errors(env) -> None:
    c = env.catalog
    ui.section("Pipeline task errors", "Most recent failures logged by the notebooks")
    if not has_table(c, "monitoring.databricks_job_logs"):
        ui.empty("No job logs yet.")
        return
    df, error = try_query(f"""
        SELECT created_at, task_key, dataset, error_type, error_message, run_id
        FROM `{c}`.monitoring.databricks_job_logs WHERE status = 'FAILED'
        ORDER BY created_at DESC LIMIT 50
    """)
    if df is None:
        ui.query_error(error, "job logs")
    elif df.empty:
        st.success("No task failures logged. ✔", icon="✅")
    else:
        st.dataframe(df, hide_index=True, width="stretch",
                     column_config={"created_at": st.column_config.DatetimeColumn("When", format="MMM DD HH:mm"),
                                    "error_message": st.column_config.TextColumn("Error", width="large")})


def render() -> None:
    env = current_env()
    ui.hero(
        "Data Quality",
        "QA runs and their test results, validation failure rates, ingestion health and quarantined "
        "records — everything you need to trust the numbers.",
        [f"Environment · {env.key}", f"Catalog · {env.catalog}", "DQ threshold · 1%"],
        overline="Operate",
    )
    _qa_runs(env)
    _silver_dq(env)
    _bronze_ingestion(env)
    _quarantine(env)
    _job_errors(env)
