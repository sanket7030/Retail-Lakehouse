from datetime import datetime, timezone

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType


def _add_corrupt_record_field(source_schema):
    if "_corrupt_record" in source_schema.fieldNames():
        return source_schema

    return StructType(
        source_schema.fields
        + [StructField("_corrupt_record", StringType(), True)]
    )


def ingest_promotions(
    spark,
    source_path: str,
    target_table: str,
    source_schema,
    environment: str,
    batch_id: str,
) -> None:

    bronze_schema = _add_corrupt_record_field(source_schema)

    df = (
        spark.read
        .format("csv")
        .option("header", "true")
        .option("mode", "PERMISSIVE")
        .option("columnNameOfCorruptRecord", "_corrupt_record")
        .schema(bronze_schema)
        .load(source_path)
    )

    df = (
        df
        .withColumn(
            "_source_file",
            F.col("_metadata.file_path"),
        )
        .withColumn(
            "_ingestion_timestamp",
            F.current_timestamp(),
        )
        .withColumn(
            "_load_date",
            F.current_date(),
        )
        .withColumn(
            "_batch_id",
            F.lit(batch_id),
        )
        .withColumn(
            "_environment",
            F.lit(environment),
        )
    )

    total_records = df.count()

    corrupt_records = df.filter(
        F.col("_corrupt_record").isNotNull()
    ).count()

    corrupt_rate_percent = (
        (corrupt_records / total_records) * 100
        if total_records > 0
        else 0.0
    )

    print(
        f"Promotions ingestion metrics: "
        f"total={total_records}, "
        f"corrupt={corrupt_records}, "
        f"corrupt_rate={corrupt_rate_percent:.2f}%"
    )

    (
        df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(target_table)
    )

    print(
        f"Promotions written to: "
        f"{target_table}"
    )