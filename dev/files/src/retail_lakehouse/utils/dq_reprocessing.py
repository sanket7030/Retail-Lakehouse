from pyspark.sql import functions as F


def reprocess_quarantine_batch(
    spark,
    quarantine_table: str,
    target_table: str,
    dataset_name: str,
    batch_id: str,
    required_columns: list[str],
    validation_rules: list[dict] | None = None,
) -> dict:
    """
    Reprocess one quarantined Bronze batch.

    Valid records are promoted to Bronze.
    Records that still fail DQ remain in quarantine.

    Idempotency is based on:
        _source_file + _batch_id + business key

    Reprocessing does not append duplicate quarantine records.
    """

    from delta.tables import DeltaTable
    from retail_lakehouse.utils.quality import add_quality_columns

    business_key_map = {
        "customers": ["customer_id"],
        "products": ["product_id"],
        "orders": ["order_id"],
        "clickstream": ["event_id"],
        "returns": ["return_id"],
        "promotions": ["promotion_id"],
    }

    key_columns = business_key_map.get(dataset_name)

    if not key_columns:
        raise ValueError(
            f"No business-key configuration for dataset '{dataset_name}'."
        )

    quarantine_df = (
        spark.table(quarantine_table)
        .filter(F.col("_batch_id") == batch_id)
    )

    if quarantine_df.limit(1).count() == 0:
        raise ValueError(
            f"No quarantined records found for dataset "
            f"'{dataset_name}' and batch '{batch_id}'."
        )

    identity_columns = [
        "_source_file",
        "_batch_id",
        *key_columns,
    ]

    # Collapse duplicate quarantine records created by previous
    # reprocessing attempts.
    reprocess_df = (
        quarantine_df
        .drop(
            "_quality_status",
            "_quality_reason",
            "_quarantine_reason",
            "_quarantine_timestamp",
            "_quarantine_batch_id",
        )
        .dropDuplicates(identity_columns)
    )

    # Re-run the complete DQ rule set.
    reprocess_df = add_quality_columns(
        reprocess_df,
        required_columns=required_columns,
        validation_rules=validation_rules,
    )

    valid_df = (
        reprocess_df
        .filter(F.col("_quality_status") == "VALID")
        .drop("_quality_status", "_quality_reason")
        .dropDuplicates(identity_columns)
    )

    invalid_df = (
        reprocess_df
        .filter(F.col("_quality_status") == "QUARANTINE")
        .dropDuplicates(identity_columns)
    )

    valid_count = valid_df.count()
    invalid_count = invalid_df.count()

    new_valid_count = 0

    # ---------------------------------------------------------
    # Promote valid records to Bronze.
    # ---------------------------------------------------------
    if valid_count > 0:

        if spark.catalog.tableExists(target_table):

            existing_identity_df = (
                spark.table(target_table)
                .select(*identity_columns)
                .dropDuplicates(identity_columns)
            )

            new_valid_df = valid_df.join(
                existing_identity_df,
                on=identity_columns,
                how="left_anti",
            )

        else:
            new_valid_df = valid_df

        new_valid_count = new_valid_df.count()

        if new_valid_count > 0:
            (
                new_valid_df
                .write
                .format("delta")
                .mode("append")
                .saveAsTable(target_table)
            )

    # ---------------------------------------------------------
    # Synchronize quarantine state.
    #
    # Remove the existing records for this batch and replace
    # them with only the records that still fail DQ.
    #
    # This prevents duplicate quarantine records on retries.
    # ---------------------------------------------------------
    quarantine_table_exists = spark.catalog.tableExists(
        quarantine_table
    )

    if quarantine_table_exists:

        quarantine_delta = DeltaTable.forName(
            spark,
            quarantine_table,
        )

        quarantine_delta.delete(
            F.col("_batch_id") == batch_id
        )

    if invalid_count > 0:

        (
            invalid_df
            .withColumn(
                "_quarantine_reason",
                F.coalesce(
                    F.col("_quality_reason"),
                    F.lit(
                        "DQ validation failed during reprocessing"
                    ),
                ),
            )
            .withColumn(
                "_quarantine_timestamp",
                F.current_timestamp(),
            )
            .withColumn(
                "_quarantine_batch_id",
                F.lit(batch_id),
            )
            .drop(
                "_quality_status",
                "_quality_reason",
            )
            .write
            .format("delta")
            .mode("append")
            .saveAsTable(quarantine_table)
        )

    result = {
        "dataset": dataset_name,
        "batch_id": batch_id,
        "valid_records": valid_count,
        "invalid_records": invalid_count,
        "new_bronze_records": new_valid_count,
        "status": "PASS" if invalid_count == 0 else "PARTIAL",
    }

    print(
        "DQ reprocessing result: "
        f"dataset={dataset_name}, "
        f"batch_id={batch_id}, "
        f"valid={valid_count}, "
        f"invalid={invalid_count}, "
        f"new_bronze={new_valid_count}, "
        f"status={result['status']}"
    )

    return result