"""Build genie/genie_space_prod.json: the PROD Genie Agent behind Ask AI's "Genie" engine.

The JSON is the agent's parsed `serialized_space` (tables, example SQL, instructions, sample questions).
Edit this script, regenerate, then push the change to the agent:

    python genie/build_space.py
    databricks genie update-space 01f1c0ace0ad1b2cbce08a2b45b1b417 --json @<body.json>
      where body.json = {"serialized_space": "<genie_space_prod.json as a JSON string>"}

Run every example SQL against the catalog before pushing: Genie copies them, so a broken example
teaches it a broken query.
"""
import json
import pathlib

C = "retail_prod"
OUT = pathlib.Path(__file__).parent / "genie_space_prod.json"

TABLES = [f"{C}.gold.{t}" for t in (
    "customer_revenue_summary", "customer_sales_summary", "daily_sales_summary", "dim_customer", "dim_date",
    "dim_product", "fact_orders", "fact_returns", "monthly_sales_summary", "product_revenue_summary",
    "product_sales_summary", "promotion_product_summary")]
TABLES += [f"{C}.monitoring.{t}" for t in (
    "bronze_ingestion_metrics", "databricks_job_logs", "qa_run_summary", "qa_test_results", "silver_dq_metrics")]
TABLES += [f"{C}.silver_quarantine.{t}" for t in ("customers", "orders", "promotions", "returns")]

SAMPLE_QUESTIONS = [
    "What was net revenue by month this year?",
    "Top 10 products by net revenue, with their category",
    "Did the latest QA run have any failures or warnings?",
    "Which dataset has the highest data-quality failure rate?",
    "Why were orders quarantined?",
]

EXAMPLES = [
    ("What was net revenue by month this year?",
     f"SELECT year, month, net_sales_amount, refund_amount, net_revenue\nFROM {C}.gold.monthly_sales_summary\n"
     "WHERE year = year(current_date())\nORDER BY month"),
    ("Top 10 products by net revenue",
     f"SELECT p.product_name, p.category, r.units_sold, r.net_revenue\nFROM {C}.gold.product_revenue_summary r\n"
     f"JOIN {C}.gold.dim_product p ON r.product_id = p.product_id\nORDER BY r.net_revenue DESC\nLIMIT 10"),
    ("Top 10 customers by net revenue",
     f"SELECT c.customer_id, concat_ws(' ', c.first_name, c.last_name) AS customer_name, c.customer_segment,\n"
     f"       r.order_count, r.net_revenue\nFROM {C}.gold.customer_revenue_summary r\n"
     f"JOIN {C}.gold.dim_customer c ON r.customer_id = c.customer_id AND c.is_current = true\n"
     "ORDER BY r.net_revenue DESC\nLIMIT 10"),
    ("Summarize the latest QA run",
     "SELECT qa_run_id, status, total_tests, passed, warnings, failed, pass_rate_percent, started_at, duration_seconds\n"
     f"FROM {C}.monitoring.qa_run_summary\nORDER BY started_at DESC\nLIMIT 1"),
    ("Which tests did not pass in the latest QA run?",
     "SELECT layer, test_name, status, actual, expected, details\n"
     f"FROM {C}.monitoring.qa_test_results\n"
     f"WHERE qa_run_id = (SELECT qa_run_id FROM {C}.monitoring.qa_run_summary ORDER BY started_at DESC LIMIT 1)\n"
     "  AND status <> 'PASS'\nORDER BY status, layer, test_name"),
    ("Latest data-quality status per dataset",
     "SELECT dataset, dq_status, total_records, valid_records, quarantined_records, dq_failure_rate_percent,\n"
     "       dq_failure_threshold_percent, recorded_at\n"
     f"FROM {C}.monitoring.silver_dq_metrics\n"
     "QUALIFY row_number() OVER (PARTITION BY dataset ORDER BY recorded_at DESC) = 1\n"
     "ORDER BY dq_failure_rate_percent DESC"),
    ("Why were orders quarantined?",
     "SELECT trim(reason) AS reason, count(*) AS records\n"
     f"FROM (SELECT explode(split(_quality_reason, ';')) AS reason FROM {C}.silver_quarantine.orders)\n"
     "GROUP BY 1\nORDER BY records DESC"),
    ("Which product category had the most refunds?",
     "SELECT p.category, count(*) AS returns, round(sum(r.refund_amount), 2) AS refund_amount\n"
     f"FROM {C}.gold.fact_returns r\n"
     f"JOIN {C}.gold.fact_orders o ON r.order_id = o.order_id\n"
     f"JOIN {C}.gold.dim_product p ON o.product_id = p.product_id\n"
     "GROUP BY p.category\nORDER BY refund_amount DESC"),
    ("How many returns reference orders that don't exist?",
     "SELECT count(*) AS orphan_returns, round(sum(r.refund_amount), 2) AS orphan_refund_amount\n"
     f"FROM {C}.gold.fact_returns r\n"
     f"LEFT ANTI JOIN {C}.gold.fact_orders o ON r.order_id = o.order_id"),
]

INSTRUCTIONS = f"""You answer questions about GlobalMart's retail lakehouse in the PROD catalog `{C}`.
Tables:
- gold: star schema. fact_orders (order_id, customer_id, product_id, order_date, quantity, unit_price, discount_amount, gross_amount, net_sales_amount, payment_method, order_status), fact_returns (return_id, order_id, customer_id, product_id, return_date, return_quantity, refund_amount, return_reason, return_status), dim_customer (first_name, last_name, customer_segment; SCD Type 2: effective_start_date, effective_end_date, is_current), dim_product (product_id, product_name, category, subcategory, brand, unit_price), dim_date. Summaries: daily_sales_summary (order_date), monthly_sales_summary (year, month), product_revenue_summary / customer_revenue_summary (order_count, units_sold, gross_sales_amount, discount_amount, net_sales_amount, refund_amount, net_revenue), product_sales_summary / customer_sales_summary (no refunds), promotion_product_summary (promotion_id, promotion_name, product_id, product_name, category, brand, start_date, end_date, discount_percent).
- monitoring: qa_run_summary (one row per QA run: qa_run_id, status PASS/WARN/FAIL, total_tests, passed, warnings, failed, pass_rate_percent, started_at, finished_at, duration_seconds), qa_test_results (one row per test, joined by qa_run_id: layer, test_name, status, actual, expected, details), silver_dq_metrics (one row per dataset per batch: dq_failure_rate_percent, dq_failure_threshold_percent, dq_status PASS/ALERT), bronze_ingestion_metrics (rescued/corrupt record rates, ingestion_status OK/ALERT), databricks_job_logs (task-level pipeline logs).
- silver_quarantine: rows rejected by Silver data-quality rules for customers, orders, promotions, returns; `_quality_reason` holds semicolon-separated reasons.

Metric definitions:
- gross_amount = quantity * unit_price; net_sales_amount = gross_amount - discount_amount.
- net_revenue = net_sales_amount - refund_amount. Prefer the *_revenue_summary, daily and monthly tables for revenue.
- Many fact_returns rows reference order_ids that are not in fact_orders ("orphan returns"). Revenue summaries only count refunds for returns whose order exists; do the same when computing from facts, and mention orphan returns when refunds are discussed.
- IMPORTANT: fact_returns.product_id usually does NOT match dim_product (about 145 of 160 returns). For the product, category or brand of a return, join fact_returns to fact_orders on order_id and use fact_orders.product_id -> dim_product. Never join fact_returns.product_id to dim_product directly. Say that orphan returns (order not in fact_orders) are excluded.
- Return rate = total refund_amount / total net_sales_amount unless the user asks about units.
- Current customer attributes: dim_customer WHERE is_current = true.
- A data-quality ALERT means the failure rate exceeded the 1% threshold.

How to answer:
- Show names, not only IDs: join dim_product or dim_customer (is_current = true).
- For QA questions use the latest run by started_at unless a qa_run_id is given, and always state the qa_run_id.
- For data-quality status take the latest row per dataset by recorded_at.
- For "why quarantined" questions, split and count _quality_reason; never guess reasons.
- When summarizing results (best/worst month, peaks, totals), base the summary on ALL returned rows, not only the first few.
- When asked "by how much", give the difference to the next-best value.
- Format money as USD with two decimals."""


def hid(prefix: int, n: int) -> str:
    return f"{prefix}{n:031d}"


space = {
    "version": 2,
    "config": {"sample_questions": [{"id": hid(1, i), "question": [q]} for i, q in enumerate(SAMPLE_QUESTIONS, 1)]},
    "data_sources": {"tables": [{"identifier": t} for t in sorted(TABLES)]},
    "instructions": {
        "example_question_sqls": [
            {"id": hid(2, i), "question": [q], "sql": [line + "\n" for line in sql.split("\n")[:-1]] + [sql.split("\n")[-1]]}
            for i, (q, sql) in enumerate(EXAMPLES, 1)
        ],
        "text_instructions": [{"id": hid(3, 1), "content": [line + "\n" for line in INSTRUCTIONS.split("\n")]}],
    },
}
OUT.write_text(json.dumps(space, indent=2), encoding="utf-8")

print(f"wrote {OUT.name}: {len(TABLES)} tables, {len(EXAMPLES)} example SQLs, {len(SAMPLE_QUESTIONS)} sample questions")
