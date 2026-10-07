import uuid
from datetime import datetime, timezone

from pyspark.sql.types import (
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)


def get_job_context(spark, dbutils) -> dict:
    context = dbutils.notebook.entry_point.getDbutils().notebook().getContext()

    def get_tag_value(name: str) -> str | None:
        try:
            value = context.tags().get(name)
            return value.get() if value.isDefined() else None
        except Exception:
            return None

    def get_context_value(name: str) -> str | None:
        try:
            value = getattr(context, name)()
            return value.get() if value.isDefined() else None
        except Exception:
            return None

    def get_spark_conf(name: str) -> str | None:
        try:
            value = spark.conf.get(name, None)
            return value if value else None
        except Exception:
            return None

    job_id = (
        get_tag_value("jobId")
        or get_context_value("jobId")
        or get_spark_conf("spark.databricks.job.id")
    )

    run_id = (
        get_tag_value("jobRunId")
        or get_spark_conf("spark.databricks.job.runId")
    )

    task_run_id = (
        get_tag_value("taskRunId")
        or get_spark_conf("spark.databricks.job.taskRunId")
    )

    return {
        "job_id": job_id,
        "run_id": run_id,
        "task_run_id": task_run_id,
    }


def log_cell(
    spark,
    catalog: str,
    environment: str,
    job_context: dict,
    task_key: str,
    notebook_name: str,
    cell_name: str,
    domain: str,
    dataset: str,
    status: str,
    rows_processed: int = 0,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:

    start_time = datetime.now(timezone.utc)

    job_id = job_context.get("job_id")
    run_id = job_context.get("run_id")
    task_run_id = job_context.get("task_run_id")

    end_time = datetime.now(timezone.utc)

    duration_ms = int(
        (end_time - start_time).total_seconds() * 1000
    )

    row = [(
        str(uuid.uuid4()),
        environment,
        job_id,
        run_id,
        task_run_id,
        task_key,
        notebook_name,
        cell_name,
        domain,
        dataset,
        status,
        start_time,
        end_time,
        duration_ms,
        rows_processed,
        error_type,
        error_message,
        datetime.now(timezone.utc),
    )]

    schema = StructType([
        StructField("log_id", StringType(), False),
        StructField("environment", StringType(), True),

        StructField("job_id", StringType(), True),
        StructField("run_id", StringType(), True),
        StructField("task_run_id", StringType(), True),
        StructField("task_key", StringType(), True),

        StructField("notebook_name", StringType(), True),
        StructField("cell_name", StringType(), True),

        StructField("domain", StringType(), True),
        StructField("dataset", StringType(), True),

        StructField("status", StringType(), True),

        StructField("start_time", TimestampType(), True),
        StructField("end_time", TimestampType(), True),
        StructField("duration_ms", LongType(), True),

        StructField("rows_processed", LongType(), True),

        StructField("error_type", StringType(), True),
        StructField("error_message", StringType(), True),

        StructField("created_at", TimestampType(), True),
    ])

    log_df = spark.createDataFrame(
        row,
        schema=schema,
    )

    (
        log_df.write
        .format("delta")
        .mode("append")
        .saveAsTable(
            f"{catalog}.monitoring.databricks_job_logs"
        )
    )