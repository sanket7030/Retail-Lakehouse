import streamlit as st

from core import charts, ui
from core.config import current_env
from core.data import has_table, try_query

METRICS = {
    "Net revenue": ("net_revenue", True),
    "Net sales": ("net_sales_amount", True),
    "Units sold": ("units_sold", False),
    "Refunds": ("refund_amount", True),
}


def _needs(c: str, *tables: str) -> bool:
    missing = [t for t in tables if not has_table(c, f"gold.{t}")]
    if missing:
        ui.empty(f"Missing Gold table(s): {', '.join(missing)}", "Run the end-to-end pipeline first.")
    return not missing


def _trend(c: str) -> None:
    ui.section("Revenue over time", "Net revenue after discounts and refunds")
    grain = st.segmented_control("Granularity", ["Monthly", "Daily"], default="Monthly", key="trend_grain",
                                 label_visibility="collapsed")
    if grain == "Daily":
        if not _needs(c, "daily_sales_summary"):
            return
        df, error = try_query(f"SELECT order_date AS period, net_revenue FROM `{c}`.gold.daily_sales_summary ORDER BY 1")
    else:
        if not _needs(c, "monthly_sales_summary"):
            return
        df, error = try_query(
            f"SELECT make_date(year, month, 1) AS period, net_revenue FROM `{c}`.gold.monthly_sales_summary ORDER BY 1"
        )
    if df is None:
        ui.query_error(error, "the revenue trend")
    elif df.empty:
        ui.empty("No sales yet.")
    else:
        charts.line(df, "period", "net_revenue", y_title="Net revenue", height=300)


def _products(c: str, top_n: int, metric_label: str) -> None:
    metric, is_money = METRICS[metric_label]
    left, right = st.columns(2, gap="large")
    with left:
        ui.section(f"Top {top_n} products", f"by {metric_label.lower()}")
        if _needs(c, "product_revenue_summary", "dim_product"):
            df, error = try_query(f"""
                SELECT coalesce(d.product_name, p.product_id) AS product, p.{metric} AS value
                FROM `{c}`.gold.product_revenue_summary p
                LEFT JOIN `{c}`.gold.dim_product d USING (product_id)
                ORDER BY value DESC NULLS LAST LIMIT {top_n}
            """)
            if df is None:
                ui.query_error(error, "top products")
            else:
                charts.hbar(df, "product", "value", value_title=metric_label, money=is_money)
    with right:
        ui.section("By category", f"{metric_label.lower()} per product category")
        if _needs(c, "product_revenue_summary", "dim_product"):
            df, error = try_query(f"""
                SELECT coalesce(d.category, 'Unknown') AS category, SUM(p.{metric}) AS value
                FROM `{c}`.gold.product_revenue_summary p
                LEFT JOIN `{c}`.gold.dim_product d USING (product_id)
                GROUP BY 1 ORDER BY value DESC NULLS LAST LIMIT 12
            """)
            if df is None:
                ui.query_error(error, "category breakdown")
            else:
                charts.hbar(df, "category", "value", value_title=metric_label, money=is_money, slot=2)


def _customers(c: str, top_n: int) -> None:
    left, right = st.columns([2, 3], gap="large")
    with left:
        ui.section("Customer segments", "Net revenue by current segment")
        if _needs(c, "customer_revenue_summary", "dim_customer"):
            df, error = try_query(f"""
                SELECT coalesce(d.customer_segment, 'Unknown') AS segment, SUM(r.net_revenue) AS net_revenue
                FROM `{c}`.gold.customer_revenue_summary r
                LEFT JOIN (SELECT * FROM `{c}`.gold.dim_customer WHERE is_current) d USING (customer_id)
                GROUP BY 1 ORDER BY 2 DESC
            """)
            if df is None:
                ui.query_error(error, "segments")
            else:
                charts.vbar(df, "segment", "net_revenue", value_title="Net revenue")
    with right:
        ui.section(f"Top {top_n} customers", "Highest lifetime net revenue")
        if _needs(c, "customer_revenue_summary", "dim_customer"):
            df, error = try_query(f"""
                SELECT r.customer_id, concat_ws(' ', d.first_name, d.last_name) AS customer,
                       d.customer_segment AS segment, d.city, r.order_count, r.net_sales_amount,
                       r.refund_amount, r.net_revenue
                FROM `{c}`.gold.customer_revenue_summary r
                LEFT JOIN (SELECT * FROM `{c}`.gold.dim_customer WHERE is_current) d USING (customer_id)
                ORDER BY r.net_revenue DESC NULLS LAST LIMIT {top_n}
            """)
            if df is None:
                ui.query_error(error, "top customers")
            else:
                money = st.column_config.NumberColumn(format="dollar")
                st.dataframe(df, hide_index=True, width="stretch", column_config={
                    "customer_id": "ID", "customer": "Customer", "segment": "Segment", "city": "City",
                    "order_count": st.column_config.NumberColumn("Orders", format="%d"),
                    "net_sales_amount": money, "refund_amount": money,
                    "net_revenue": st.column_config.ProgressColumn(
                        "Net revenue", format="$%.0f", min_value=0,
                        max_value=float(df["net_revenue"].max() or 1)),
                })


def _returns_and_payments(c: str) -> None:
    left, right = st.columns(2, gap="large")
    with left:
        ui.section("Returns by reason", "Refunded amount · all returns, incl. ones without a matching order")
        if _needs(c, "fact_returns"):
            df, error = try_query(f"""
                SELECT coalesce(return_reason, 'Unspecified') AS reason, SUM(refund_amount) AS refunds
                FROM `{c}`.gold.fact_returns GROUP BY 1 ORDER BY 2 DESC LIMIT 10
            """)
            if df is None:
                ui.query_error(error, "returns")
            else:
                charts.hbar(df, "reason", "refunds", value_title="Refunds", slot=1)
    with right:
        ui.section("Payment methods", "Net sales by payment method")
        if _needs(c, "fact_orders"):
            df, error = try_query(f"""
                SELECT coalesce(payment_method, 'Unknown') AS method, SUM(net_sales_amount) AS net_sales
                FROM `{c}`.gold.fact_orders GROUP BY 1 ORDER BY 2 DESC
            """)
            if df is None:
                ui.query_error(error, "payment methods")
            else:
                charts.hbar(df, "method", "net_sales", value_title="Net sales", slot=6)


def _promotions(c: str) -> None:
    ui.section("Promotions", "Active today, then upcoming")
    if not _needs(c, "promotion_product_summary"):
        return
    df, error = try_query(f"""
        SELECT * FROM (
          SELECT CASE WHEN current_date() BETWEEN start_date AND end_date THEN 'ACTIVE'
                      WHEN start_date > current_date() THEN 'UPCOMING' ELSE 'ENDED' END AS state,
                 promotion_name, product_name, category, brand, discount_percent, start_date, end_date
          FROM `{c}`.gold.promotion_product_summary
        )
        ORDER BY CASE state WHEN 'ACTIVE' THEN 0 WHEN 'UPCOMING' THEN 1 ELSE 2 END,
                 product_name IS NULL, start_date
        LIMIT 200
    """)
    if df is None:
        ui.query_error(error, "promotions")
        return
    counts = df["state"].value_counts()
    unmatched = int(df["product_name"].isna().sum())
    st.caption(f"**{counts.get('ACTIVE', 0)}** active · **{counts.get('UPCOMING', 0)}** upcoming · "
               f"**{counts.get('ENDED', 0)}** ended (first 200 shown)")
    if unmatched:
        st.caption(f"{unmatched} of {len(df)} promotions reference a product_id that isn't in gold.dim_product "
                   "— shown with “—” for product details.")
    view = df.fillna({"product_name": "—", "category": "—", "brand": "—"})
    st.dataframe(view, hide_index=True, width="stretch", height=320, column_config={
        "state": "State", "promotion_name": "Promotion", "product_name": "Product",
        "category": "Category", "brand": "Brand",
        "discount_percent": st.column_config.NumberColumn("Discount", format="%.0f%%"),
        "start_date": st.column_config.DateColumn("Start"), "end_date": st.column_config.DateColumn("End"),
    })


def render() -> None:
    env = current_env()
    c = env.catalog
    ui.hero(
        "Business Insights",
        "Revenue, products, customers, returns and promotions — straight from the Gold layer.",
        [f"Environment · {env.key}", "Source · gold.*"],
        overline="Analyze",
    )
    f1, f2, _ = st.columns([2, 2, 3])
    metric = f1.selectbox("Product metric", list(METRICS), index=0)
    top_n = f2.slider("Top N", 5, 25, 10, step=5)

    _trend(c)
    _products(c, top_n, metric)
    _customers(c, top_n)
    _returns_and_payments(c)
    _promotions(c)
