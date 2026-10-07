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


INGESTION_METRICS_SCHEMA = StructType(
    [
        StructField("environment", StringType(), False),
        StructField("dataset", StringType(), False),
        StructField("batch_id", StringType(), False),
        StructField("micro_batch_id", IntegerType(), False),
        StructField("total_records", IntegerType(), False),
        StructField("rescued_records", IntegerType(), False),
        StructField("corrupt_records", IntegerType(), False),
        StructField("rescued_rate_percent", DoubleType(), False),
        StructField("corrupt_rate_percent", DoubleType(), False),
        StructField(
            "ingestion_alert_threshold_percent",
            DoubleType(),
            False,
        ),
        StructField("ingestion_status", StringType(), False),
        StructField("recorded_at", TimestampType(), True),
    ]
)


def calculate_ingestion_metrics(
    batch_df: DataFrame,
    environment: str,
    dataset: str,
    batch_id: str,
    micro_batch_id: int,
    alert_threshold_percent: float = 1.0,
) -> dict:
    rescued_expr = (
        F.col("_rescued_data").isNotNull()
        & (F.length(F.trim(F.col("_rescued_data"))) > 0)
        if "_rescued_data" in batch_df.columns
        else F.lit(False)
    )

    corrupt_expr = (
        F.col("_corrupt_record").isNotNull()
        & (F.length(F.trim(F.col("_corrupt_record"))) > 0)
        if "_corrupt_record" in batch_df.columns
        else F.lit(False)
    )

    aggregates = (
        batch_df
        .agg(
            F.count("*").alias("total_records"),
            F.sum(
                F.when(rescued_expr, 1).otherwise(0)
            ).alias("rescued_records"),
            F.sum(
                F.when(corrupt_expr, 1).otherwise(0)
            ).alias("corrupt_records"),
        )
        .collect()[0]
    )

    total_records = int(aggregates["total_records"])
    rescued_records = int(aggregates["rescued_records"] or 0)
    corrupt_records = int(aggregates["corrupt_records"] or 0)

    rescued_rate_percent = (
        rescued_records / total_records * 100
        if total_records > 0
        else 0.0
    )

    corrupt_rate_percent = (
        corrupt_records / total_records * 100
        if total_records > 0
        else 0.0
    )

    ingestion_status = (
        "ALERT"
        if max(rescued_rate_percent, corrupt_rate_percent)
        > alert_threshold_percent
        else "OK"
    )

    return {
        "environment": environment,
        "dataset": dataset,
        "batch_id": batch_id,
        "micro_batch_id": micro_batch_id,
        "total_records": total_records,
        "rescued_records": rescued_records,
        "corrupt_records": corrupt_records,
        "rescued_rate_percent": rescued_rate_percent,
        "corrupt_rate_percent": corrupt_rate_percent,
        "ingestion_alert_threshold_percent": alert_threshold_percent,
        "ingestion_status": ingestion_status,
        "recorded_at": None,
    }


def write_ingestion_metrics(
    spark,
    catalog: str,
    metrics: dict,
) -> None:
    target_table = f"{catalog}.monitoring.bronze_ingestion_metrics"

    metrics_df = spark.createDataFrame(
        [metrics],
        schema=INGESTION_METRICS_SCHEMA,
    ).withColumn(
        "recorded_at",
        F.current_timestamp(),
    )

    if not spark.catalog.tableExists(target_table):
        (
            metrics_df.write
            .format("delta")
            .mode("overwrite")
            .saveAsTable(target_table)
        )
        return

    metrics_df.createOrReplaceTempView(
        "bronze_ingestion_metrics_source"
    )

    spark.sql(
        f"""
        MERGE INTO {target_table} AS target
        USING bronze_ingestion_metrics_source AS source
        ON target.environment = source.environment
        AND target.dataset = source.dataset
        AND target.batch_id = source.batch_id
        AND target.micro_batch_id = source.micro_batch_id

        WHEN MATCHED THEN UPDATE SET
            target.total_records =
                source.total_records,
            target.rescued_records =
                source.rescued_records,
            target.corrupt_records =
                source.corrupt_records,
            target.rescued_rate_percent =
                source.rescued_rate_percent,
            target.corrupt_rate_percent =
                source.corrupt_rate_percent,
            target.ingestion_alert_threshold_percent =
                source.ingestion_alert_threshold_percent,
            target.ingestion_status =
                source.ingestion_status,
            target.recorded_at =
                source.recorded_at

        WHEN NOT MATCHED THEN INSERT (
            environment,
            dataset,
            batch_id,
            micro_batch_id,
            total_records,
            rescued_records,
            corrupt_records,
            rescued_rate_percent,
            corrupt_rate_percent,
            ingestion_alert_threshold_percent,
            ingestion_status,
            recorded_at
        )
        VALUES (
            source.environment,
            source.dataset,
            source.batch_id,
            source.micro_batch_id,
            source.total_records,
            source.rescued_records,
            source.corrupt_records,
            source.rescued_rate_percent,
            source.corrupt_rate_percent,
            source.ingestion_alert_threshold_percent,
            source.ingestion_status,
            source.recorded_at
        )
        """
    )