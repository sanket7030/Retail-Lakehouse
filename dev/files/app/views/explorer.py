import streamlit as st

from core import ui
from core.config import SCHEMAS, current_env
from core.data import QueryError, ensure_read_only, execute, existing_tables, list_catalogs, try_query

EXAMPLES = {
    "Daily revenue (last 30 days)":
        "SELECT order_date, order_count, net_sales_amount, refund_amount, net_revenue\n"
        "FROM {c}.gold.daily_sales_summary\nORDER BY order_date DESC\nLIMIT 30",
    "Customers with segment history (SCD2)":
        "SELECT customer_id, COUNT(*) AS versions, collect_list(customer_segment) AS segments\n"
        "FROM {c}.gold.dim_customer\nGROUP BY customer_id\nHAVING COUNT(*) > 1\nORDER BY versions DESC\nLIMIT 50",
    "Latest QA failures":
        "SELECT recorded_at, layer, test_name, actual, expected, details\n"
        "FROM {c}.monitoring.qa_test_results\nWHERE status = 'FAIL'\nORDER BY recorded_at DESC\nLIMIT 50",
    "Quarantine reasons — orders":
        "SELECT _quality_reason, COUNT(*) AS records\nFROM {c}.silver_quarantine.orders\n"
        "GROUP BY _quality_reason\nORDER BY records DESC",
}


def _browser(default_catalog: str) -> None:
    ui.section("Table browser", "Preview, schema and profile of any table in any readable catalog")
    catalogs = list_catalogs() or [default_catalog]
    if default_catalog not in catalogs:
        catalogs = [default_catalog, *catalogs]

    s0, s1, s2 = st.columns([1, 1, 2])
    c = s0.selectbox("Catalog", catalogs, index=catalogs.index(default_catalog), key="explorer_catalog")
    tables = existing_tables(c)
    known = [s for s in SCHEMAS if any(t.startswith(f"{s}.") for t in tables)]
    schemas = known + sorted({t.split(".", 1)[0] for t in tables} - set(known))
    if not schemas:
        s1.selectbox("Schema", [], disabled=True)
        ui.empty(f"No tables visible in `{c}`.",
                 "The catalog is empty, or your account lacks USE CATALOG / SELECT on it.")
        return

    schema = s1.selectbox("Schema", schemas, index=schemas.index("gold") if "gold" in schemas else 0)
    names = sorted(t.split(".", 1)[1] for t in tables if t.startswith(f"{schema}."))
    table = s2.selectbox("Table", names)
    if not table:
        return
    full = f"`{c}`.`{schema}`.`{table}`"

    preview_tab, schema_tab, profile_tab = st.tabs(["Preview", "Schema", "Profile"])
    with preview_tab:
        df, error = try_query(f"SELECT * FROM {full} LIMIT 200")
        if df is None:
            ui.query_error(error, "the preview")
        else:
            st.dataframe(df, hide_index=True, width="stretch", height=420)
            st.caption(f"First {len(df)} rows of `{c}.{schema}.{table}`")
    with schema_tab:
        df, error = try_query(f"""
            SELECT column_name, data_type, is_nullable, comment
            FROM `{c}`.information_schema.columns
            WHERE table_schema = '{schema}' AND table_name = '{table}' ORDER BY ordinal_position
        """)
        if df is None:
            ui.query_error(error, "the schema")
        else:
            st.dataframe(df, hide_index=True, width="stretch")
    with profile_tab:
        cols_df, _ = try_query(f"""
            SELECT column_name FROM `{c}`.information_schema.columns
            WHERE table_schema = '{schema}' AND table_name = '{table}' ORDER BY ordinal_position LIMIT 40
        """)
        if cols_df is None or cols_df.empty:
            ui.empty("No columns to profile.")
        else:
            exprs = ", ".join(
                f"COUNT(`{col}`) AS `{col}__nn`, COUNT(DISTINCT `{col}`) AS `{col}__nd`"
                for col in cols_df["column_name"]
            )
            stats, error = try_query(f"SELECT COUNT(*) AS __rows, {exprs} FROM {full}")
            if stats is None:
                ui.query_error(error, "the profile")
            else:
                row = stats.iloc[0]
                total = int(row["__rows"])
                profile = [{
                    "column": col,
                    "non_null": int(row[f"{col}__nn"]),
                    "null_pct": (1 - row[f"{col}__nn"] / total) * 100 if total else 0,
                    "distinct": int(row[f"{col}__nd"]),
                } for col in cols_df["column_name"]]
                st.metric("Rows", f"{total:,}")
                st.dataframe(profile, hide_index=True, width="stretch", column_config={
                    "null_pct": st.column_config.ProgressColumn("Null %", min_value=0, max_value=100, format="%.1f%%"),
                })


def _workbench(c: str) -> None:
    ui.section("SQL workbench", "Read-only queries against the selected environment")
    example = st.selectbox("Start from an example", ["—"] + list(EXAMPLES), key="sql_example")
    if example != "—" and st.session_state.get("_last_example") != example:
        st.session_state["sql_text"] = EXAMPLES[example].format(c=c)
        st.session_state["_last_example"] = example

    sql = st.text_area("SQL", key="sql_text", height=180,
                       placeholder=f"SELECT * FROM {c}.gold.fact_orders LIMIT 100")
    run = st.button("Run query", type="primary", icon=":material/play_arrow:")
    if run and sql.strip():
        try:
            with st.spinner("Running on the SQL warehouse…"):
                df = execute(ensure_read_only(sql), row_limit=10000)
            st.session_state["sql_result"] = df
        except (QueryError, Exception) as exc:
            st.session_state.pop("sql_result", None)
            st.error(str(exc)[:1500])

    df = st.session_state.get("sql_result")
    if df is not None:
        st.caption(f"{len(df):,} rows (max 10,000)")
        st.dataframe(df, hide_index=True, width="stretch", height=420)
        st.download_button("Download CSV", df.to_csv(index=False).encode(), "query_result.csv",
                           "text/csv", icon=":material/download:")


def render() -> None:
    env = current_env()
    ui.hero(
        "Data Explorer",
        "Browse every catalog, schema and table the app can read, profile columns, and run ad-hoc SQL.",
        [f"Environment · {env.key}", f"Catalogs readable · {len(list_catalogs())}", "Read-only"],
    )
    _browser(env.catalog)
    _workbench(env.catalog)
