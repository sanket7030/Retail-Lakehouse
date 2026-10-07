# Retail Lakehouse (Databricks free account)

Code lives in `Retail-Lakehouse/Retail_Lakehouse/` (bundle: `databricks.yml`, app in `app/`, jobs in `resources/`, SQL helpers in `scripts/`).

## Environment
- Databricks CLI is NOT on PATH: `$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Databricks.DatabricksCLI_Microsoft.Winget.Source_8wekyb3d8bbwe\databricks.exe`. git is not on PATH either.
- Profile: `new` (https://dbc-8e8728a6-551c.cloud.databricks.com). Always pass `-p new`.
- SQL warehouse: Serverless Starter Warehouse (`f7c38881dd7a3cfb`). LLM endpoint: `databricks-gpt-oss-120b`.
- Python HTTPS to the workspace hits CERTIFICATE_VERIFY_FAILED (TLS inspection); prefer the CLI, or `pip install pip-system-certs` in the venv.

## Skill routing (skills are in `.claude/skills/`)
Load `databricks-core` first for any CLI/auth/bundle work, then the product skill:
- Data questions / SQL / exploring tables → `databricks-data-discovery`, `databricks-dbsql`, `databricks-genie`
- Unity Catalog grants, catalogs, volumes → `databricks-unity-catalog`
- Bundle deploys (`bundle deploy/run -t dev`) → `databricks-dabs`; jobs → `databricks-jobs`; DLT/Lakeflow → `databricks-pipelines`
- The Streamlit QA app → `databricks-apps-python`, `databricks-apps`, `databricks-app-design`
- Dashboards → `databricks-aibi-dashboards`; metric views → `databricks-metric-views`
- Test data → `databricks-synthetic-data-gen`; streaming → `databricks-spark-structured-streaming`
- MLflow / agents / tracing → `mlflow-onboarding`, `agent-evaluation`, `retrieving-mlflow-traces`, `databricks-model-serving`
- Unknown API detail → `databricks-docs` before guessing
- Architecture questions → `graphify` (a graph already exists in `Retail_Lakehouse/graphify-out/`)
- Launch video → `/brag` (previous output in `brag-output/`)
