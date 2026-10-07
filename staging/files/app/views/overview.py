import streamlit as st

from core import charts, ui
from core.config import current_env
from core.data import has_table, try_query
from core.jobs import last_run
from views.shared import latest_dq, layer_counts, qa_runs


def render() -> None:
    env = current_env()
    c = env.catalog

    ui.hero(
        "GlobalMart Retail Lakehouse",
        "Command center for the Bronze → Silver → Gold pipeline: business performance, "
        "data quality and QA health at a glance.",
        [f"Environment · {env.key}", f"Catalog · {c}", "Datasets · 6", "Gold tables · 12"],
        overline="Operate",
    )

    # ------------------------------------------------------------------ business KPIs
    ui.section("Business performance", "All-time, from Gold facts")
    if has_table(c, "gold.fact_orders") and has_table(c, "gold.fact_returns"):
        df, error = try_query(f"""
            -- Same definition as the Gold summaries: refunds only count when the return's order exists.
            SELECT o.net_sales, o.gross, o.orders, o.customers, o.units,
                   r.refunds, r.returns, r.orphan_returns, r.orphan_refunds
            FROM (SELECT SUM(net_sales_amount) net_sales, SUM(gross_amount) gross,
                         COUNT(DISTINCT order_id) orders, COUNT(DISTINCT customer_id) customers,
                         SUM(quantity) units
                  FROM `{c}`.gold.fact_orders) o
            CROSS JOIN (
                SELECT COALESCE(SUM(CASE WHEN fo.order_id IS NOT NULL THEN fr.refund_amount END), 0) refunds,
                       COUNT_IF(fo.order_id IS NOT NULL) returns,
                       COUNT_IF(fo.order_id IS NULL) orphan_returns,
                       COALESCE(SUM(CASE WHEN fo.order_id IS NULL THEN fr.refund_amount END), 0) orphan_refunds
                FROM `{c}`.gold.fact_returns fr
                LEFT JOIN (SELECT DISTINCT order_id FROM `{c}`.gold.fact_orders) fo ON fr.order_id = fo.order_id
            ) r
        """)
        if df is None:
            ui.query_error(error, "business KPIs")
        else:
            k = df.iloc[0]
            net_revenue = (k.net_sales or 0) - (k.refunds or 0)
            return_rate = (k.refunds / k.net_sales * 100) if k.net_sales else 0
            aov = (k.net_sales / k.orders) if k.orders else 0
            cols = st.columns(4)
            with cols[0]:
                ui.kpi("Net revenue", ui.money(net_revenue), f"Net sales {ui.money(k.net_sales)} − refunds")
            with cols[1]:
                ui.kpi("Orders", ui.number(k.orders), f"Avg order {ui.money(aov)}")
            with cols[2]:
                ui.kpi("Customers", ui.number(k.customers), f"{ui.number(k.units)} units sold")
            with cols[3]:
                ui.kpi("Refund rate", f"{return_rate:.1f}%",
                       f"{ui.number(k.returns)} returns · {ui.money(k.refunds)} refunded")
            if k.orphan_returns:
                st.warning(
                    f"{int(k.orphan_returns)} returns ({ui.money(k.orphan_refunds)} in refunds) reference orders that "
                    "don't exist in gold.fact_orders. They are excluded above, matching the Gold summaries — "
                    "see the QA referential-integrity test in Data Quality.",
                    icon="⚠️",
                )
    else:
        ui.empty("Gold facts aren't built yet in this environment.", "Run the end-to-end pipeline from Pipeline Control.")

    # ------------------------------------------------------------------ platform health
    ui.section("Platform health", "Latest pipeline, QA and data-quality signals")
    cols = st.columns(4)

    with cols[0]:
        run = None
        try:
            run = last_run(env.e2e_job) if env.e2e_job else None
        except Exception:
            pass
        if run:
            duration = f" · {run['duration_min']} min" if run.get("duration_min") else ""
            ui.kpi("Last E2E pipeline", ui.badge(run["status"]), f"Started {ui.ago(run['started'])}{duration}", value_html=True)
        else:
            ui.kpi("Last E2E pipeline", "—", "No runs found or job not configured")

    with cols[1]:
        runs, _ = qa_runs(env, limit=1)
        if runs is not None and not runs.empty:
            qa = runs.iloc[0]
            ui.kpi("Latest QA run", f"{float(qa.pass_rate_percent or 0):.0f}% pass",
                   f"✔ {int(qa.passed)} · ▲ {int(qa.warnings)} · ✖ {int(qa.failed)} — {ui.ago(qa.started_at)}"
                   f" · {qa.qa_run_id}")
        else:
            ui.kpi("Latest QA run", "—", "No QA results stored yet")

    dq, _ = latest_dq(env)
    with cols[2]:
        if dq is not None and not dq.empty:
            alerts = int((dq["dq_status"] == "ALERT").sum())
            worst = dq.iloc[0]
            ui.kpi("DQ alerts", f"{alerts} / {len(dq)}",
                   f"Worst: {worst.dataset} at {worst.dq_failure_rate_percent:.2f}%")
        else:
            ui.kpi("DQ alerts", "—", "No DQ metrics yet")

    counts_df, counts_error = layer_counts(env)
    with cols[3]:
        if counts_df is not None:
            quarantined = int(counts_df["silver_quarantine"].sum())
            total = int(counts_df["silver"].sum()) + quarantined
            ui.kpi("Quarantined records", ui.number(quarantined),
                   f"{(quarantined / total * 100 if total else 0):.2f}% of Silver input")
        else:
            ui.kpi("Quarantined records", "—", "No Silver tables yet")

    # ------------------------------------------------------------------ trend + medallion
    left, right = st.columns([3, 2], gap="large")
    with left:
        ui.section("Net revenue trend", "Daily, after discounts and refunds")
        if has_table(c, "gold.daily_sales_summary"):
            trend, error = try_query(
                f"SELECT order_date, net_revenue FROM `{c}`.gold.daily_sales_summary ORDER BY order_date"
            )
            if trend is None:
                ui.query_error(error, "the revenue trend")
            elif trend.empty:
                ui.empty("No sales yet.")
            else:
                charts.line(trend, "order_date", "net_revenue", y_title="Net revenue", height=320)
        else:
            ui.empty("daily_sales_summary not found.")

    with right:
        ui.section("Medallion flow", "Rows per dataset")
        if counts_df is None:
            if counts_error:
                ui.query_error(counts_error, "layer counts")
            else:
                ui.empty("No Bronze/Silver tables yet.")
        else:
            st.dataframe(
                counts_df,
                hide_index=True,
                width="stretch",
                column_config={
                    "dataset": st.column_config.TextColumn("Dataset"),
                    "bronze": st.column_config.NumberColumn("Bronze", format="%d"),
                    "silver": st.column_config.NumberColumn("Silver", format="%d"),
                    "silver_quarantine": st.column_config.NumberColumn("Quarantine", format="%d"),
                    "valid_pct": st.column_config.ProgressColumn(
                        "Valid %", min_value=0, max_value=100, format="%.1f%%"
                    ),
                },
            )
