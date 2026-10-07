import os
from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class Environment:
    key: str
    catalog: str
    e2e_job: str
    qa_job: str
    genie_space: str = ""  # Genie Agent used by Ask AI; empty = not set up for this environment

    @property
    def param(self) -> str:
        return self.key.lower()


ENVIRONMENTS = {
    "DEV": Environment(
        "DEV", "retail_dev",
        os.getenv("DEV_E2E_JOB_ID", ""), os.getenv("DEV_QA_JOB_ID", ""), os.getenv("DEV_GENIE_SPACE_ID", ""),
    ),
    "STAGING": Environment(
        "STAGING", "retail_staging",
        os.getenv("STAGING_E2E_JOB_ID", ""), os.getenv("STAGING_QA_JOB_ID", ""),
        os.getenv("STAGING_GENIE_SPACE_ID", ""),
    ),
    "PROD": Environment(
        "PROD", "retail_prod",
        os.getenv("PROD_E2E_JOB_ID", ""), os.getenv("PROD_QA_JOB_ID", ""), os.getenv("PROD_GENIE_SPACE_ID", ""),
    ),
}

DEFAULT_ENVIRONMENT = os.getenv("DEFAULT_ENVIRONMENT", "PROD").upper()
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "")
LLM_ENDPOINT = os.getenv("SERVING_ENDPOINT_NAME", "databricks-gpt-oss-120b")


def _parse_restrictions(raw: str) -> dict[str, frozenset[str]]:
    """'a@x.com=cat1,cat2;b@y.com=cat3' -> {email: {catalogs}}."""
    restrictions = {}
    for entry in raw.split(";"):
        email, _, catalogs = entry.partition("=")
        if email.strip() and catalogs.strip():
            restrictions[email.strip().lower()] = frozenset(
                c.strip().lower() for c in catalogs.split(",") if c.strip()
            )
    return restrictions


# Viewers who may only see the listed catalogs inside the app (on top of their Unity Catalog grants).
CATALOG_RESTRICTIONS = _parse_restrictions(os.getenv("CATALOG_RESTRICTIONS", ""))

DATASETS = ["customers", "products", "orders", "clickstream", "returns", "promotions"]

SCHEMAS = ["bronze", "bronze_quarantine", "silver", "silver_quarantine", "gold", "monitoring"]

GOLD_TABLES = [
    "dim_customer", "dim_product", "dim_date", "fact_orders", "fact_returns",
    "customer_sales_summary", "product_sales_summary", "daily_sales_summary",
    "monthly_sales_summary", "customer_revenue_summary", "product_revenue_summary",
    "promotion_product_summary",
]


def current_env() -> Environment:
    return ENVIRONMENTS[st.session_state.get("env", DEFAULT_ENVIRONMENT)]
