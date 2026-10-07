from pyspark.sql import DataFrame
from pyspark.sql.types import StringType, StructField, StructType


def _add_corrupt_record_field(source_schema):
    """
    Add Spark's corrupt-record column to the ingestion schema if it
    is not already present.
    """
    if "_corrupt_record" in source_schema.fieldNames():
        return source_schema

    return StructType(
        source_schema.fields
        + [StructField("_corrupt_record", StringType(), True)]
    )


def ingest_to_bronze(
    spark,
    source_path: str,
    schema_path: str,
    checkpoint_path: str,
    target_table: str,
    source_schema,
    environment: str,
    batch_id: str,
    catalog: str | None = None,
    dataset_name: str | None = None,
    ingestion_alert_threshold_percent: float = 1.0,
) -> None:
    from retail_lakehouse.utils.ingestion_metrics import (
        calculate_ingestion_metrics,
        write_ingestion_metrics,
    )
    from retail_lakehouse.utils.metadata import add_ingestion_metadata

    bronze_schema = _add_corrupt_record_field(source_schema)

    df = (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.schemaLocation", schema_path)
        .option("cloudFiles.schemaEvolutionMode", "rescue")
        .option("rescuedDataColumn", "_rescued_data")
        .option("columnNameOfCorruptRecord", "_corrupt_record")
        .option("mode", "PERMISSIVE")
        .option("header", "true")
        .schema(bronze_schema)
        .load(source_path)
    )

    df = add_ingestion_metadata(
        df,
        environment=environment,
        batch_id=batch_id,
    )

    def process_batch(
        batch_df: DataFrame,
        micro_batch_id: int,
    ) -> None:
        dataset = dataset_name or target_table

        metrics = calculate_ingestion_metrics(
            batch_df=batch_df,
            environment=environment,
            dataset=dataset,
            batch_id=batch_id,
            micro_batch_id=micro_batch_id,
            alert_threshold_percent=ingestion_alert_threshold_percent,
        )

        print(
            "Bronze ingestion metrics: "
            f"total={metrics['total_records']}, "
            f"rescued={metrics['rescued_records']}, "
            f"corrupt={metrics['corrupt_records']}, "
            f"rescued_rate="
            f"{metrics['rescued_rate_percent']:.2f}%, "
            f"corrupt_rate="
            f"{metrics['corrupt_rate_percent']:.2f}%, "
            f"status={metrics['ingestion_status']}"
        )

        if catalog:
            write_ingestion_metrics(
                spark=spark,
                catalog=catalog,
                metrics=metrics,
            )

        (
            batch_df.write
            .format("delta")
            .mode("append")
            .option("mergeSchema", "true")
            .saveAsTable(target_table)
        )

    query = (
        df.writeStream
        .foreachBatch(process_batch)
        .option("checkpointLocation", checkpoint_path)
        .outputMode("append")
        .trigger(availableNow=True)
        .start()
    )

    query.awaitTermination()