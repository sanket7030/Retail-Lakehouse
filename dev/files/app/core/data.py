"""SQL access to the lakehouse through a SQL warehouse (Statement Execution API).

Queries run as the signed-in viewer (Databricks Apps user authorization), so Unity Catalog grants decide
what each person can read. Jobs and the LLM endpoint still go through the app's service principal.
"""

import os
import re
import time

import pandas as pd
import streamlit as st
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Disposition, Format, StatementState

from core.config import CATALOG_RESTRICTIONS, WAREHOUSE_ID, current_env

IN_DATABRICKS_APP = bool(os.getenv("DATABRICKS_APP_NAME"))

SESSION_SCOPE_MESSAGE = (
    "SESSION_NEEDS_REAUTH: your sign-in to this app was approved before it needed SQL access, so the token "
    "Databricks forwards for you can't run queries. Open the app in a private/incognito window (or clear "
    "cookies for databricksapps.com), sign in again and accept the permission prompt."
)

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
    """The app's service principal (jobs, model serving)."""
    return WorkspaceClient()


def _header(name: str) -> str | None:
    try:
        return st.context.headers.get(name)
    except Exception:
        return None


def viewer() -> str | None:
    return _header("X-Forwarded-Email")


def _viewer_key() -> str:
    return (viewer() or "local").lower()


def sql_client() -> WorkspaceClient:
    """A client acting as the signed-in viewer. Locally (no proxy headers) it falls back to your CLI profile."""
    token = _header("X-Forwarded-Access-Token")
    if token:
        return WorkspaceClient(host=workspace().config.host, token=token, auth_type="pat")
    if IN_DATABRICKS_APP:
        raise QueryError("The app didn't receive your sign-in token. Reload the page and accept the "
                         "permission prompt; if it persists the app needs the `sql` user authorization scope.")
    return workspace()


def allowed_catalogs() -> frozenset[str] | None:
    """Catalogs the viewer may see in the app, or None when the viewer isn't restricted."""
    return CATALOG_RESTRICTIONS.get(_viewer_key())


def catalog_allowed(catalog: str) -> bool:
    allowed = allowed_catalogs()
    return allowed is None or catalog.replace("`", "").lower() in allowed


_TABLE_REF = re.compile(r"\b(?:from|join)\s+`?([\w-]+)`?\s*\.\s*`?[\w-]+`?\s*\.", re.IGNORECASE)
_QUALIFIED = re.compile(r"`?([\w-]+)`?\s*\.\s*`?[\w-]")
_SHOW_TARGET = re.compile(r"\b(?:in|from|catalog)\s+`?([\w-]+)`?", re.IGNORECASE)
_SHOW_CATALOGS = re.compile(r"^\s*show\s+catalogs\b", re.IGNORECASE)


def _check_catalogs(sql: str) -> None:
    """For restricted viewers, refuse SQL that names any catalog outside their allowlist."""
    allowed = allowed_catalogs()
    if allowed is None:
        return
    if _SHOW_CATALOGS.match(sql):
        raise QueryError("Listing catalogs isn't available here. Your catalogs: "
                         + ", ".join(f"`{c}`" for c in sorted(allowed)) + ".")
    known = {c.lower() for c in _list_catalogs(_viewer_key())}
    referenced = set(_TABLE_REF.findall(sql))
    referenced |= {c for c in _QUALIFIED.findall(sql) if c.lower() in known}
    if sql.lstrip()[:4].lower() in ("show", "desc"):
        referenced |= {c for c in _SHOW_TARGET.findall(sql) if c.lower() in known}
    if blocked := sorted(c for c in referenced if not catalog_allowed(c)):
        raise QueryError(f"You don't have access to catalog `{blocked[0]}` in this app.")


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
    _check_catalogs(without_literals)
    return sql


def execute(statement: str, row_limit: int = 5000, timeout_seconds: int = 120) -> pd.DataFrame:
    if not WAREHOUSE_ID:
        raise QueryError(
            "No SQL warehouse is configured. Add a `sql-warehouse` resource to the app."
        )

    api = sql_client().statement_execution
    try:
        response = api.execute_statement(
            statement=statement,
            warehouse_id=WAREHOUSE_ID,
            wait_timeout="30s",
            row_limit=row_limit,
            disposition=Disposition.INLINE,
            format=Format.JSON_ARRAY,
            # Restricted viewers resolve unqualified names in the retail catalog, never their own default.
            catalog=current_env().catalog if allowed_catalogs() is not None else None,
        )
    except Exception as exc:
        if "scope" in str(exc).lower():
            raise QueryError(SESSION_SCOPE_MESSAGE) from exc
        raise

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


# Cached helpers take the viewer as their first argument so one person's results never serve another.

@st.cache_data(ttl=300, show_spinner=False)
def _query(who: str, statement: str, row_limit: int) -> pd.DataFrame:
    return execute(statement, row_limit)


def query(statement: str, row_limit: int = 5000) -> pd.DataFrame:
    return _query(_viewer_key(), statement, row_limit)


def try_query(statement: str, row_limit: int = 5000) -> tuple[pd.DataFrame | None, str | None]:
    """Dashboard-friendly query: returns (df, None) or (None, error message)."""
    try:
        return query(statement, row_limit), None
    except Exception as exc:  # surfaced as an inline error state, never a crash
        return None, str(exc)


# The metadata helpers below let errors escape the cached function and swallow them outside it, so a
# failure (e.g. an expired session) is retried on the next call instead of being cached as "nothing".

def existing_tables(catalog: str) -> set[str]:
    """`schema.table` names that exist in the catalog."""
    if not catalog_allowed(catalog):
        return set()
    try:
        return _existing_tables(_viewer_key(), catalog)
    except Exception:
        return set()


@st.cache_data(ttl=300, show_spinner=False)
def _existing_tables(who: str, catalog: str) -> set[str]:
    df = execute(
        f"SELECT table_schema, table_name FROM `{catalog}`.information_schema.tables "
        "WHERE table_schema <> 'information_schema'"
    )
    return {f"{s}.{t}" for s, t in zip(df["table_schema"], df["table_name"])}


def has_table(catalog: str, name: str) -> bool:
    return name in existing_tables(catalog)


def table_columns(catalog: str, schema: str, table: str) -> set[str]:
    if not catalog_allowed(catalog):
        return set()
    try:
        return _table_columns(_viewer_key(), catalog, schema, table)
    except Exception:
        return set()


@st.cache_data(ttl=300, show_spinner=False)
def _table_columns(who: str, catalog: str, schema: str, table: str) -> set[str]:
    df = execute(
        f"SELECT column_name FROM `{catalog}`.information_schema.columns "
        f"WHERE table_schema = '{schema}' AND table_name = '{table}'"
    )
    return set(df["column_name"]) if not df.empty else set()


def list_catalogs() -> list[str]:
    """Catalogs the viewer can see (granted at least USE/BROWSE, and within any app restriction)."""
    try:
        names = _list_catalogs(_viewer_key())
    except Exception:
        return []
    return [c for c in names if catalog_allowed(c)]


@st.cache_data(ttl=600, show_spinner=False)
def _list_catalogs(who: str) -> list[str]:
    df = execute("SHOW CATALOGS")
    return sorted(df.iloc[:, 0].dropna().tolist()) if not df.empty else []


def is_permission_error(message: str) -> bool:
    text = message.upper()
    return any(k in text for k in ("INSUFFICIENT_PERMISSIONS", "PERMISSION_DENIED", "INSUFFICIENT PRIVILEGES",
                                   "DOES NOT HAVE", "USE CATALOG", "USE SCHEMA"))


def clear_cache() -> None:
    _query.clear()
    _existing_tables.clear()
    _list_catalogs.clear()
    _table_columns.clear()
