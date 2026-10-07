from datetime import datetime, timezone

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)


DQ_METRICS_SCHEMA = StructType(
    [
        StructField("environment", StringType(), False),
        StructField("dataset", StringType(), False),
        StructField("batch_id", StringType(), False),
        StructField("micro_batch_id", IntegerType(), False),
        StructField("total_records", IntegerType(), False),
        StructField("valid_records", IntegerType(), False),
        StructField("quarantined_records", IntegerType(), False),
        StructField("dq_failure_rate_percent", DoubleType(), False),
        StructField("dq_failure_threshold_percent", DoubleType(), False),
        StructField("dq_status", StringType(), False),
        StructField("recorded_at", TimestampType(), False),
    ]
)


def calculate_dq_metrics(
    batch_df: DataFrame,
    environment: str,
    dataset: str,
    batch_id: str,
    micro_batch_id: int,
    threshold_percent: float,
) -> dict:

    total_records = batch_df.count()

    if total_records == 0:
        return {
            "environment": environment,
            "dataset": dataset,
            "batch_id": batch_id,
            "micro_batch_id": micro_batch_id,
            "total_records": 0,
            "valid_records": 0,
            "quarantined_records": 0,
            "dq_failure_rate_percent": 0.0,
            "dq_failure_threshold_percent": threshold_percent,
            "dq_status": "PASS",
            "recorded_at": datetime.now(timezone.utc),
        }

    quarantined_records = (
        batch_df
        .filter(F.col("_quality_status") == "QUARANTINE")
        .count()
    )

    valid_records = (
        batch_df
        .filter(F.col("_quality_status") == "VALID")
        .count()
    )

    failure_rate_percent = (
        quarantined_records / total_records
    ) * 100.0

    dq_status = (
        "ALERT"
        if failure_rate_percent > threshold_percent
        else "PASS"
    )

    return {
        "environment": environment,
        "dataset": dataset,
        "batch_id": batch_id,
        "micro_batch_id": micro_batch_id,
        "total_records": total_records,
        "valid_records": valid_records,
        "quarantined_records": quarantined_records,
        "dq_failure_rate_percent": failure_rate_percent,
        "dq_failure_threshold_percent": threshold_percent,
        "dq_status": dq_status,
        "recorded_at": datetime.now(timezone.utc),
    }


def write_dq_metrics(
    spark,
    catalog: str,
    metrics: dict,
) -> None:

    target_table = (
        f"{catalog}.monitoring.silver_dq_metrics"
    )

    metrics_df = spark.createDataFrame(
        [metrics],
        schema=DQ_METRICS_SCHEMA,
    )

    if not spark.catalog.tableExists(target_table):
        (
            metrics_df.write
            .format("delta")
            .mode("overwrite")
            .saveAsTable(target_table)
        )
        return

    from delta.tables import DeltaTable

    target = DeltaTable.forName(
        spark,
        target_table,
    )

    (
        target.alias("target")
        .merge(
            metrics_df.alias("source"),
            """
            target.environment = source.environment
            AND target.dataset = source.dataset
            AND target.batch_id = source.batch_id
            AND target.micro_batch_id = source.micro_batch_id
            """,
        )
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )