"""'Ask anything' assistant: a tool-calling LLM grounded in the lakehouse via read-only SQL."""

import json
import re
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from core.config import DATASETS, Environment
from core.data import (allowed_catalogs, catalog_allowed, ensure_read_only, execute, existing_tables,
                       is_permission_error, list_catalogs, workspace)
from core.jobs import recent_runs

MAX_TOOL_ROUNDS = 10
MAX_TOOL_CALLS = 16
MAX_TOKENS = 2500
SQL_ROW_LIMIT = 500
ROWS_SHOWN_TO_MODEL = 60


@dataclass
class Step:
    tool: str
    args: dict
    summary: str
    sql: str | None = None
    result: pd.DataFrame | None = None
    error: str | None = None


@dataclass
class Answer:
    text: str
    steps: list[Step] = field(default_factory=list)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_catalogs",
            "description": "List every Unity Catalog catalog in the workspace that this app can read.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tables",
            "description": (
                "Search ALL catalogs in the workspace for tables or columns whose name or comment matches a "
                "keyword (e.g. 'flight', 'bakery', 'revenue'). Use this to find data outside the retail lakehouse."
            ),
            "parameters": {
                "type": "object",
                "properties": {"keyword": {"type": "string", "description": "A single keyword to search for."}},
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "List tables in a catalog (defaults to the current retail catalog), optionally for one schema.",
            "parameters": {
                "type": "object",
                "properties": {
                    "catalog": {"type": "string", "description": "Catalog name. Omit for the current retail catalog."},
                    "schema": {"type": "string", "description": "Optional schema filter."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_table",
            "description": "Get the column names and types of a table. Use before writing SQL against an unfamiliar table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string",
                              "description": "catalog.schema.table (or schema.table for the current retail catalog)"}
                },
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": (
                "Run ONE read-only Databricks SQL query (SELECT/WITH) against the lakehouse and get rows back. "
                "Always use fully-qualified names catalog.schema.table. Aggregate in SQL rather than pulling raw rows."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The SQL query."},
                    "purpose": {"type": "string", "description": "One short line on what this query answers."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recent_job_runs",
            "description": "Recent runs (status, start time, duration) of the end-to-end pipeline job or the QA job.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job": {"type": "string", "enum": ["e2e", "qa"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["job"],
            },
        },
    },
]


def system_prompt(env: Environment) -> str:
    c = env.catalog
    catalogs = ", ".join(f"`{name}`" for name in list_catalogs()) or "(unknown — call list_catalogs)"
    return f"""You are the GlobalMart data assistant, embedded in the Retail Lakehouse QA & operations app.
You answer questions about ANY data in this Databricks workspace — first and foremost the retail lakehouse
(business data, data quality, QA results, pipeline runs), but also every other catalog the app can read.
Current retail environment: {env.key}, Unity Catalog catalog `{c}`.

## Data available in the workspace
Catalogs the app can read: {catalogs}.
- Questions about sales, customers, products, orders, returns, promotions, QA or data quality → use the
  retail catalog `{c}` described below (other retail_* catalogs are the other environments).
- Anything else (e.g. bakery, flights, ML tables) or when unsure where data lives → call search_tables
  with a keyword, or list_tables for a catalog, then describe_table, then run_sql. Never say data doesn't
  exist without searching first.
{"- Only the catalogs listed above are available to this user. Never query any other catalog (including "
 "`system`); use `<catalog>.information_schema` for metadata." if allowed_catalogs() is not None else
 "- `system.information_schema` describes every table/column the app can see across all catalogs."}

## Architecture (medallion)
- `{c}.bronze.<dataset>` raw ingested CSV data + technical columns (_source_file, _ingestion_timestamp,
  _load_date, _batch_id, _environment, sometimes _rescued_data/_corrupt_record).
- `{c}.bronze_quarantine.<dataset>` records rejected at ingestion.
- `{c}.silver.<dataset>` validated, cleaned data. `{c}.silver_quarantine.<dataset>` rows failing DQ rules,
  with `_quality_reason` (semicolon-separated reasons) and `_quality_status`.
- Datasets: {", ".join(DATASETS)} (ERP: customers, products, orders; e-commerce: clickstream, returns;
  marketing: promotions).
- `{c}.gold`: dim_customer (SCD2: effective_start_date, effective_end_date, is_current), dim_product,
  dim_date, fact_orders (order_id, customer_id, product_id, order_date, quantity, unit_price,
  discount_amount, gross_amount, net_sales_amount, payment_method, order_status), fact_returns (return_id,
  order_id, customer_id, product_id, return_date, return_quantity, refund_amount, return_reason,
  return_status), dim_product (product_id, product_name, category, subcategory, brand, unit_price,
  currency), product_revenue_summary / customer_revenue_summary (product_id / customer_id, order_count,
  units_sold, gross_sales_amount, discount_amount, net_sales_amount, refund_amount, net_revenue),
  daily_sales_summary (order_date + the same measures), monthly_sales_summary (year, month + the same
  measures), customer_sales_summary / product_sales_summary (no refunds), promotion_product_summary
  (promotion_id, promotion_name, product_id, product_name, category, brand, start_date, end_date,
  discount_percent).
- `{c}.monitoring`: qa_run_summary (one row per QA run: qa_run_id, environment, status PASS/WARN/FAIL,
  total_tests, passed, warnings, failed, pass_rate_percent, started_at, finished_at, duration_seconds,
  triggered_by, job_id, job_run_id), qa_test_results (one row per test: qa_run_id, environment, layer,
  test_name, status PASS/WARN/FAIL, actual, expected, details, recorded_at). QA run ids look like
  QA-PROD-20261002-143015-a1b2c3; older runs have ids ending in -legacy.
  silver_dq_metrics (dataset, batch_id, total_records, valid_records, quarantined_records,
  dq_failure_rate_percent, dq_failure_threshold_percent, dq_status PASS/ALERT, recorded_at),
  bronze_ingestion_metrics (rescued/corrupt counts and rates, ingestion_status OK/ALERT),
  databricks_job_logs (task_key, notebook_name, dataset, status, rows_processed, error_type,
  error_message, created_at).

## Metric definitions
- gross_amount = quantity * unit_price; net_sales_amount = gross_amount - discount_amount.
- net_revenue = net_sales_amount - refund_amount (refunds come from returns).
- Many fact_returns rows reference order_ids that are NOT in fact_orders ("orphan returns"). Revenue
  figures (the *_revenue_summary / daily / monthly tables) only count refunds of returns whose order
  exists — do the same (join to fact_orders) and mention orphan returns when relevant.
- Return rate = total refund_amount / total net_sales_amount, unless the user means units.
- Current customer attributes: dim_customer WHERE is_current = true.

## DQ rules applied in Silver
Required (non-null) columns per dataset, plus: valid email (customers), unit_price > 0 (products,
orders), quantity > 0 and discount_amount >= 0 (orders), return_quantity > 0 and refund_amount >= 0
(returns), 0 <= discount_percent <= 100 and end_date >= start_date (promotions). DQ status is ALERT when
the failure rate exceeds the 1% threshold.

## Query recipes (follow these patterns)
- Revenue by product/customer: use the *_revenue_summary table's `net_revenue` and JOIN dim_product
  (product_name, category) or dim_customer (WHERE is_current) so answers show names, not just IDs.
- QA runs: list/compare runs from {c}.monitoring.qa_run_summary (ORDER BY started_at DESC). For the tests
  of a run, filter qa_test_results by qa_run_id. Latest run's tests:
  SELECT layer, test_name, status, actual, expected, details FROM {c}.monitoring.qa_test_results
  WHERE qa_run_id = (SELECT qa_run_id FROM {c}.monitoring.qa_run_summary ORDER BY started_at DESC LIMIT 1)
  Always mention the qa_run_id you are reporting on.
- Latest DQ status per dataset: silver_dq_metrics has one row per batch; take the latest per dataset with
  row_number() OVER (PARTITION BY dataset ORDER BY recorded_at DESC) = 1.
- WHY records were quarantined: never guess. Query the actual reasons:
  SELECT trim(r) AS reason, count(*) AS records
  FROM (SELECT explode(split(_quality_reason, ';')) AS r FROM {c}.silver_quarantine.<dataset>)
  GROUP BY 1 ORDER BY 2 DESC
  (only datasets that have rejections have a silver_quarantine table — use list_tables to check).

## How to work
- NEVER invent numbers or causes. For anything data-related, call run_sql (use describe_table first if
  unsure of columns). Prefer Gold tables for business questions, monitoring tables for quality/QA
  questions. A question with several parts usually needs several queries — run them all.
- Only read-only SQL. Use fully-qualified names (`{c}.schema.table`). Aggregate in SQL; add LIMIT.
- Be efficient — you have a limited number of tool calls. Combine work into one query where possible,
  e.g. count several tables at once:
  SELECT 'a' AS tbl, count(*) AS n FROM cat.s.a UNION ALL SELECT 'b', count(*) FROM cat.s.b
  Only look at tables relevant to the question; stop and answer as soon as you can.
- If a query errors, read the error, fix the SQL and retry (at most twice).
- If a tool reports a permission problem, tell the user exactly which catalog/table the app cannot read
  and that their account needs USE CATALOG, USE SCHEMA and SELECT on it — don't retry it.
- Answer concisely in Markdown: lead with the direct answer (bold the key number), then a small
  table if useful, then a one-line note on how it was computed or any caveat. Format money as $1,234.
- For conceptual questions (how the pipeline works, what a rule means) answer directly without tools.
- If the data needed doesn't exist, say so plainly and suggest what would be needed.
"""


def _frame_to_model(df: pd.DataFrame) -> str:
    shown = df.head(ROWS_SHOWN_TO_MODEL)
    payload = {
        "row_count": len(df),
        "columns": list(df.columns),
        "rows": json.loads(shown.to_json(orient="values", date_format="iso")),
    }
    if len(df) > ROWS_SHOWN_TO_MODEL:
        payload["note"] = f"Only the first {ROWS_SHOWN_TO_MODEL} rows are shown."
    return json.dumps(payload, default=str)


_IDENT = re.compile(r"[\w-]+")


def _error_payload(exc: Exception) -> str:
    message = str(exc)[:1500]
    payload = {"error": message}
    if "SESSION_NEEDS_REAUTH" in message:
        payload["session_problem"] = ("Not a data permission issue. Tell the user exactly what the error says: "
                                      "reopen the app in a private window, sign in and accept the prompt.")
    elif is_permission_error(message):
        payload["permission_problem"] = (
            "The signed-in user is not allowed to read this object. Tell them their account needs "
            "USE CATALOG, USE SCHEMA and SELECT on the catalog."
        )
    return json.dumps(payload)


def _run_tool(name: str, args: dict, env: Environment) -> tuple[str, Step]:
    if name == "list_catalogs":
        names = list_catalogs()
        return json.dumps({"catalogs": names}), Step(name, args, f"Found {len(names)} readable catalogs")

    if name == "search_tables":
        keyword = re.sub(r"[^\w -]", "", str(args.get("keyword", ""))).strip().lower()[:60]
        if not keyword:
            return json.dumps({"error": "Give a keyword"}), Step(name, args, "Empty search", error="no keyword")
        like = f"'%{keyword}%'"
        allowed = allowed_catalogs()
        scope = (f"AND t.table_catalog IN ({', '.join(repr(c) for c in sorted(allowed))})"
                 if allowed is not None else "")
        sql = f"""
            SELECT t.table_catalog, t.table_schema, t.table_name, t.comment,
                   collect_set(c.column_name) FILTER (WHERE lower(c.column_name) LIKE {like}) AS matching_columns
            FROM system.information_schema.tables t
            LEFT JOIN system.information_schema.columns c
              ON c.table_catalog = t.table_catalog AND c.table_schema = t.table_schema AND c.table_name = t.table_name
            WHERE t.table_schema <> 'information_schema' AND t.table_catalog NOT IN ('system') {scope}
            GROUP BY ALL
            HAVING lower(t.table_name) LIKE {like} OR lower(t.table_schema) LIKE {like}
                OR lower(t.table_catalog) LIKE {like} OR lower(coalesce(t.comment, '')) LIKE {like}
                OR size(matching_columns) > 0
            ORDER BY t.table_catalog, t.table_schema, t.table_name
            LIMIT 60
        """
        df = execute(sql)
        step = Step(name, args, f"Searched the workspace for “{keyword}” — {len(df)} match(es)", sql=sql.strip(), result=df)
        return _frame_to_model(df), step

    if name == "list_tables":
        catalog = str(args.get("catalog") or env.catalog).replace("`", "")
        schema = args.get("schema")
        if not _IDENT.fullmatch(catalog):
            return json.dumps({"error": "Invalid catalog name"}), Step(name, args, "Invalid catalog", error=catalog)
        if not catalog_allowed(catalog):
            return (json.dumps({"error": f"Catalog {catalog} is not available to this user."}),
                    Step(name, args, f"No access to `{catalog}`", error="catalog not available"))
        tables = sorted(t for t in existing_tables(catalog) if not schema or t.startswith(f"{schema}."))
        step = Step(name, args, f"Listed {len(tables)} tables in `{catalog}`" + (f".`{schema}`" if schema else ""))
        if not tables:
            return json.dumps({"catalog": catalog, "tables": [],
                               "note": "No tables visible — the catalog may be empty or not readable by the app."}), step
        return json.dumps({"catalog": catalog, "tables": tables[:400]}), step

    if name == "describe_table":
        table = str(args.get("table", "")).replace("`", "")
        parts = table.split(".")
        if len(parts) == 2:
            parts = [env.catalog, *parts]
        if len(parts) != 3 or not all(_IDENT.fullmatch(p) for p in parts):
            return (json.dumps({"error": "Use catalog.schema.table"}),
                    Step(name, args, "Invalid table name", error="Use catalog.schema.table"))
        catalog, schema, tbl = parts
        if not catalog_allowed(catalog):
            return (json.dumps({"error": f"Catalog {catalog} is not available to this user."}),
                    Step(name, args, f"No access to `{catalog}`", error="catalog not available"))
        sql = (
            f"SELECT column_name, data_type, comment FROM `{catalog}`.information_schema.columns "
            f"WHERE table_schema = '{schema}' AND table_name = '{tbl}' ORDER BY ordinal_position"
        )
        try:
            df = execute(sql)
        except Exception as exc:
            return _error_payload(exc), Step(name, args, f"Couldn't describe `{catalog}.{schema}.{tbl}`", error=str(exc))
        step = Step(name, args, f"Described `{catalog}.{schema}.{tbl}` ({len(df)} columns)", result=df)
        if df.empty:
            return json.dumps({"error": f"Table {catalog}.{schema}.{tbl} not found or not readable"}), step
        return json.dumps({r.column_name: f"{r.data_type}" + (f" — {r.comment}" if r.comment else "")
                           for r in df.itertuples()}), step

    if name == "run_sql":
        raw = str(args.get("query", ""))
        purpose = args.get("purpose") or "Ran a query"
        try:
            sql = ensure_read_only(raw)
            df = execute(sql, row_limit=SQL_ROW_LIMIT)
        except Exception as exc:
            return _error_payload(exc), Step(name, args, purpose, sql=raw, error=str(exc))
        return _frame_to_model(df), Step(name, args, purpose, sql=sql, result=df)

    if name == "recent_job_runs":
        job = args.get("job", "e2e")
        job_id = env.e2e_job if job == "e2e" else env.qa_job
        limit = int(args.get("limit") or 5)
        df = recent_runs(job_id, limit=limit) if job_id else pd.DataFrame()
        label = "end-to-end pipeline" if job == "e2e" else "QA"
        step = Step(name, args, f"Fetched last {len(df)} {label} job runs", result=df)
        if not job_id:
            return json.dumps({"error": f"The {label} job is not configured for {env.key}."}), step
        return _frame_to_model(df.drop(columns=["url"], errors="ignore")), step

    return json.dumps({"error": f"Unknown tool {name}"}), Step(name, args, "Unknown tool", error=name)


def _text(content) -> str:
    """Message content as plain text. Reasoning models (e.g. gpt-oss) return a list of blocks
    such as [{"type": "reasoning", ...}, {"type": "text", "text": "..."}]; keep only the text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    for block in content if isinstance(content, list) else [content]:
        kind = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
        if kind in (None, "text", "output_text") and isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


def ask(
    question: str,
    history: list[dict],
    env: Environment,
    endpoint: str,
    on_step: Callable[[Step], None] | None = None,
) -> Answer:
    """Run the tool loop until the model produces a final answer."""
    client = workspace().serving_endpoints.get_open_ai_client()
    messages = [{"role": "system", "content": system_prompt(env)}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history[-10:] if m.get("content")]
    messages.append({"role": "user", "content": question})

    steps: list[Step] = []
    for _ in range(MAX_TOOL_ROUNDS):
        if len(steps) >= MAX_TOOL_CALLS:
            break
        response = client.chat.completions.create(
            model=endpoint, messages=messages, tools=TOOLS, tool_choice="auto",
            temperature=0.1, max_tokens=MAX_TOKENS,
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []

        text = _text(message.content).strip()
        if not tool_calls:
            if text:
                return Answer(text, steps)
            break  # empty reply (seen with reasoning models): ask for a final answer below

        messages.append({
            "role": "assistant",
            "content": text or None,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
                for tc in tool_calls
            ],
        })
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                content, step = _run_tool(tc.function.name, args, env)
            except Exception as exc:
                content = json.dumps({"error": str(exc)[:1500]})
                step = Step(tc.function.name, args, "Tool failed", error=str(exc))
            steps.append(step)
            if on_step:
                on_step(step)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

    # Out of budget: make the model answer from what it has gathered instead of giving up.
    messages.append({
        "role": "user",
        "content": "Stop calling tools now. Answer my question using only the results gathered so far. "
                   "If something is incomplete, say briefly what is missing.",
    })
    try:
        response = client.chat.completions.create(
            model=endpoint, messages=messages, temperature=0.1, max_tokens=MAX_TOKENS,
        )
        text = _text(response.choices[0].message.content).strip()
    except Exception:
        text = ""
    return Answer(
        text or "I ran out of steps before reaching an answer. Try narrowing the question "
                "(e.g. a specific catalog, table or time range).",
        steps,
    )
