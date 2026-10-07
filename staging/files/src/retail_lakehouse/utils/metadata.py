from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def add_ingestion_metadata(
    df: DataFrame,
    environment: str,
    batch_id: str,
) -> DataFrame:
    return (
        df
        .withColumn("_ingestion_timestamp", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("_load_date", F.current_date())
        .withColumn("_batch_id", F.lit(batch_id))
        .withColumn("_environment", F.lit(environment))
    )