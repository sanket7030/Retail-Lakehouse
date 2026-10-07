"""SQL access to the lakehouse through a SQL warehouse (Statement Execution API)."""

import re
import time

import pandas as pd
import streamlit as st
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Disposition, Format, StatementState

from core.config import WAREHOUSE_ID

_NUMERIC = {"BYTE", "SHORT", "INT", "LONG", "FLOAT", "DOUBLE", "DECIMAL"}
_TEMPORAL = {"DATE", "TIMESTAMP", "TIMESTAMP_NTZ"}
_READ_ONLY_START = {"select", "with", "show", "describe", "desc", "explain"}
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|create|alter|truncate|grant|revoke|"
    r"copy|optimize|vacuum|refresh|call|msck|restore|clone|undrop)\b",
    re.IGNORECASE,
)


class QueryError(RuntimeError):
    pass


@st.cache_resource
def workspace() -> WorkspaceClient:
    return WorkspaceClient()


def ensure_read_only(statement: str) -> str:
    """Reject anything other than a single read-only statement."""
    sql = re.sub(r"--[^\n]*|/\*.*?\*/", " ", statement, flags=re.DOTALL).strip()
    sql = sql.rstrip("; \n\t")
    without_literals = re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", "''", sql)

    if not sql:
        raise QueryError("The query is empty.")
    if ";" in without_literals:
        raise QueryError("Only a single statement can be run at a time.")
    if without_literals.split(None, 1)[0].lower() not in _READ_ONLY_START:
        raise QueryError("Only read-only queries (SELECT / WITH / SHOW / DESCRIBE) are allowed.")
    if match := _FORBIDDEN.search(without_literals):
        raise QueryError(f"'{match.group(0).upper()}' is not allowed — this workspace is read-only here.")
    return sql


def execute(statement: str, row_limit: int = 5000, timeout_seconds: int = 120) -> pd.DataFrame:
    if not WAREHOUSE_ID:
        raise QueryError(
            "No SQL warehouse is configured. Add a `sql-warehouse` resource to the app."
        )

    api = workspace().statement_execution
    response = api.execute_statement(
        statement=statement,
        warehouse_id=WAREHOUSE_ID,
        wait_timeout="30s",
        row_limit=row_limit,
        disposition=Disposition.INLINE,
        format=Format.JSON_ARRAY,
    )

    deadline = time.time() + timeout_seconds
    while response.status.state in (StatementState.PENDING, StatementState.RUNNING):
        if time.time() > deadline:
            api.cancel_execution(response.statement_id)
            raise QueryError(f"Query timed out after {timeout_seconds}s.")
        time.sleep(1)
        response = api.get_statement(response.statement_id)

    if response.status.state != StatementState.SUCCEEDED:
        error = response.status.error
        raise QueryError(error.message if error else str(response.status.state))

    columns = (response.manifest.schema.columns or []) if response.manifest and response.manifest.schema else []
    rows = list(response.result.data_array or []) if response.result else []

    next_chunk = response.result.next_chunk_index if response.result else None
    while next_chunk is not None:
        chunk = api.get_statement_result_chunk_n(response.statement_id, next_chunk)
        rows.extend(chunk.data_array or [])
        next_chunk = chunk.next_chunk_index

    df = pd.DataFrame(rows, columns=[c.name for c in columns])
    for column in columns:
        type_name = column.type_name.value if column.type_name else ""
        if type_name in _NUMERIC:
            df[column.name] = pd.to_numeric(df[column.name], errors="coerce")
        elif type_name in _TEMPORAL:
            df[column.name] = pd.to_datetime(df[column.name], errors="coerce")
        elif type_name == "BOOLEAN":
            df[column.name] = df[column.name].map({"true": True, "false": False})
    return df


@st.cache_data(ttl=300, show_spinner=False)
def query(statement: str, row_limit: int = 5000) -> pd.DataFrame:
    return execute(statement, row_limit)


def try_query(statement: str, row_limit: int = 5000) -> tuple[pd.DataFrame | None, str | None]:
    """Dashboard-friendly query: returns (df, None) or (None, error message)."""
    try:
        return query(statement, row_limit), None
    except Exception as exc:  # surfaced as an inline error state, never a crash
        return None, str(exc)


@st.cache_data(ttl=300, show_spinner=False)
def existing_tables(catalog: str) -> set[str]:
    """`schema.table` names that exist in the catalog."""
    try:
        df = execute(
            f"SELECT table_schema, table_name FROM `{catalog}`.information_schema.tables "
            "WHERE table_schema <> 'information_schema'"
        )
    except Exception:
        return set()
    return {f"{s}.{t}" for s, t in zip(df["table_schema"], df["table_name"])}


def has_table(catalog: str, name: str) -> bool:
    return name in existing_tables(catalog)


@st.cache_data(ttl=300, show_spinner=False)
def table_columns(catalog: str, schema: str, table: str) -> set[str]:
    try:
        df = execute(
            f"SELECT column_name FROM `{catalog}`.information_schema.columns "
            f"WHERE table_schema = '{schema}' AND table_name = '{table}'"
        )
    except Exception:
        return set()
    return set(df["column_name"]) if not df.empty else set()


@st.cache_data(ttl=600, show_spinner=False)
def list_catalogs() -> list[str]:
    """Catalogs the app can see (i.e. has been granted at least USE/BROWSE on)."""
    try:
        df = execute("SHOW CATALOGS")
    except Exception:
        return []
    return sorted(df.iloc[:, 0].dropna().tolist()) if not df.empty else []


def is_permission_error(message: str) -> bool:
    text = message.upper()
    return any(k in text for k in ("INSUFFICIENT_PERMISSIONS", "PERMISSION_DENIED", "INSUFFICIENT PRIVILEGES",
                                   "DOES NOT HAVE", "USE CATALOG", "USE SCHEMA"))


def clear_cache() -> None:
    query.clear()
    existing_tables.clear()
    list_catalogs.clear()
    table_columns.clear()
