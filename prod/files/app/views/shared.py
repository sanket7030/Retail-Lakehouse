"""Queries reused by more than one page."""

import re

import pandas as pd

from core.config import DATASETS, Environment
from core.data import has_table, table_columns, try_query

# Rows written before qa_run_id existed are grouped by the minute they were recorded in;
# the QA notebook backfills them with exactly this id on its next run.
_LEGACY_RUN_ID = (
    "concat('QA-', upper(environment), '-', "
    "date_format(date_trunc('MINUTE', recorded_at), 'yyyyMMdd-HHmm'), '-legacy')"
)


def _has_run_ids(env: Environment) -> bool:
    return "qa_run_id" in table_columns(env.catalog, "monitoring", "qa_test_results")


def qa_runs(env: Environment, limit: int = 30) -> tuple[pd.DataFrame | None, str | None]:
    """One row per QA run, newest first."""
    c = env.catalog
    if has_table(c, "monitoring.qa_run_summary"):
        return try_query(f"""
            SELECT qa_run_id, status, total_tests, passed, warnings, failed, pass_rate_percent,
                   started_at, finished_at, duration_seconds, triggered_by, job_run_id
            FROM `{c}`.monitoring.qa_run_summary
            WHERE lower(environment) = '{env.param}'
            ORDER BY started_at DESC LIMIT {int(limit)}
        """)
    if not has_table(c, "monitoring.qa_test_results"):
        return None, None
    run_id = f"coalesce(qa_run_id, {_LEGACY_RUN_ID})" if _has_run_ids(env) else _LEGACY_RUN_ID
    return try_query(f"""
        SELECT run_id AS qa_run_id,
               CASE WHEN failed > 0 THEN 'FAIL' WHEN warnings > 0 THEN 'WARN' ELSE 'PASS' END AS status,
               total_tests, passed, warnings, failed,
               round(passed * 100.0 / total_tests, 2) AS pass_rate_percent,
               started_at, finished_at, CAST(NULL AS DOUBLE) AS duration_seconds,
               'legacy' AS triggered_by, CAST(NULL AS STRING) AS job_run_id
        FROM (
          SELECT {run_id} AS run_id, count(*) AS total_tests,
                 sum(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) AS passed,
                 sum(CASE WHEN status = 'WARN' THEN 1 ELSE 0 END) AS warnings,
                 sum(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) AS failed,
                 min(recorded_at) AS started_at, max(recorded_at) AS finished_at
          FROM `{c}`.monitoring.qa_test_results
          WHERE lower(environment) = '{env.param}'
          GROUP BY 1
        )
        ORDER BY started_at DESC LIMIT {int(limit)}
    """)


def qa_run_tests(env: Environment, qa_run_id: str) -> tuple[pd.DataFrame | None, str | None]:
    """All test rows of one QA run, failures first."""
    if not re.fullmatch(r"[\w-]+", qa_run_id or ""):
        return None, "Invalid QA run id"
    c = env.catalog
    if not has_table(c, "monitoring.qa_test_results"):
        return None, None
    run_id = f"coalesce(qa_run_id, {_LEGACY_RUN_ID})" if _has_run_ids(env) else _LEGACY_RUN_ID
    return try_query(f"""
        SELECT upper(layer) AS layer, test_name, status, actual, expected, details, recorded_at
        FROM `{c}`.monitoring.qa_test_results
        WHERE lower(environment) = '{env.param}' AND {run_id} = '{qa_run_id}'
        ORDER BY CASE status WHEN 'FAIL' THEN 0 WHEN 'WARN' THEN 1 ELSE 2 END, layer, test_name
    """)


def latest_qa_run(env: Environment) -> tuple[dict | None, pd.DataFrame | None, str | None]:
    """(run summary row, its tests, error) for the most recent QA run."""
    runs, error = qa_runs(env, limit=1)
    if runs is None or runs.empty:
        return None, None, error
    run = runs.iloc[0].to_dict()
    tests, error = qa_run_tests(env, run["qa_run_id"])
    return run, tests, error


def latest_dq(env: Environment) -> tuple[pd.DataFrame | None, str | None]:
    c = env.catalog
    if not has_table(c, "monitoring.silver_dq_metrics"):
        return None, None
    return try_query(f"""
        SELECT dataset, batch_id, total_records, valid_records, quarantined_records,
               dq_failure_rate_percent, dq_failure_threshold_percent, dq_status, recorded_at
        FROM (
          SELECT *, row_number() OVER (PARTITION BY dataset ORDER BY recorded_at DESC) AS rn
          FROM `{c}`.monitoring.silver_dq_metrics
        ) WHERE rn = 1 ORDER BY dq_failure_rate_percent DESC
    """)


def layer_counts(env: Environment) -> tuple[pd.DataFrame | None, str | None]:
    """Row counts per dataset across bronze / silver / silver_quarantine."""
    c = env.catalog
    parts = [
        f"SELECT '{ds}' AS dataset, '{layer}' AS layer, COUNT(*) AS n FROM `{c}`.{layer}.{ds}"
        for ds in DATASETS
        for layer in ("bronze", "silver", "silver_quarantine")
        if has_table(c, f"{layer}.{ds}")
    ]
    if not parts:
        return None, None
    df, error = try_query(" UNION ALL ".join(parts))
    if df is None:
        return None, error
    pivot = (
        df.pivot_table(index="dataset", columns="layer", values="n", aggfunc="sum")
        .reindex(columns=["bronze", "silver", "silver_quarantine"])
        .reindex(DATASETS)
        .fillna(0)
        .astype(int)
        .reset_index()
    )
    total = pivot["silver"] + pivot["silver_quarantine"]
    pivot["valid_pct"] = (pivot["silver"] / total.where(total > 0)).fillna(0) * 100
    return pivot, None
