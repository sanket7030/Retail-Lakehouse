from delta.tables import DeltaTable
from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def build_customer_scd2_source(customers_df: DataFrame) -> DataFrame:
    return (
        customers_df
        .select(
            "customer_id",
            "first_name",
            "last_name",
            "email",
            "city",
            "state",
            "country",
            "signup_date",
            "customer_segment",
        )
        .withColumn("effective_start_date", F.current_date())
        .withColumn("effective_end_date", F.lit("9999-12-31").cast("date"))
        .withColumn("is_current", F.lit(True))
    )


def merge_customer_scd2(
    spark,
    source_df: DataFrame,
    target_table: str,
) -> None:
    if not spark.catalog.tableExists(target_table):
        source_df.write.format("delta").mode("overwrite").saveAsTable(target_table)
        return

    target = DeltaTable.forName(spark, target_table)
    target_df = spark.table(target_table)

    compare_columns = [
        "first_name",
        "last_name",
        "email",
        "city",
        "state",
        "country",
        "signup_date",
        "customer_segment",
    ]

    change_condition = " OR ".join(
        [
            f"NOT (target.`{column}` <=> source.`{column}`)"
            for column in compare_columns
        ]
    )

    changed_customers = (
        source_df.alias("source")
        .join(
            target_df.alias("target"),
            (
                (F.col("source.customer_id") == F.col("target.customer_id"))
                & F.col("target.is_current")
            ),
            "inner",
        )
        .where(F.expr(change_condition))
        .select("source.*")
        .dropDuplicates(["customer_id"])
    )

    if changed_customers.limit(1).count() > 0:
        (
            target.alias("target")
            .merge(
                changed_customers.alias("source"),
                """
                target.customer_id = source.customer_id
                AND target.is_current = true
                """,
            )
            .whenMatchedUpdate(
                set={
                    "effective_end_date": "date_sub(source.effective_start_date, 1)",
                    "is_current": "false",
                }
            )
            .execute()
        )

    target_df = spark.table(target_table)

    new_customers = (
        source_df.alias("source")
        .join(
            target_df.alias("target"),
            (
                (F.col("source.customer_id") == F.col("target.customer_id"))
                & F.col("target.is_current")
            ),
            "left_anti",
        )
        .dropDuplicates(["customer_id"])
    )

    if new_customers.limit(1).count() > 0:
        new_customers.write.format("delta").mode("append").saveAsTable(target_table)

    changed_customers_to_insert = (
        changed_customers
        .withColumn("effective_start_date", F.current_date())
        .withColumn("effective_end_date", F.lit("9999-12-31").cast("date"))
        .withColumn("is_current", F.lit(True))
    )

    if changed_customers_to_insert.limit(1).count() > 0:
        changed_customers_to_insert.write.format("delta").mode("append").saveAsTable(
            target_table
        )


def build_fact_orders(orders_df: DataFrame) -> DataFrame:
    return (
        orders_df
        .withColumn(
            "gross_amount",
            F.col("quantity") * F.col("unit_price"),
        )
        .withColumn(
            "net_sales_amount",
            (
                F.col("quantity") * F.col("unit_price")
            )
            - F.coalesce(
                F.col("discount_amount"),
                F.lit(0.0),
            ),
        )
        .select(
            "order_id",
            "customer_id",
            "product_id",
            "order_date",
            "quantity",
            "unit_price",
            "discount_amount",
            "gross_amount",
            "net_sales_amount",
            "payment_method",
            "order_status",
            "_ingestion_timestamp",
            "_source_file",
        )
    )


def build_fact_returns(returns_df: DataFrame) -> DataFrame:
    return (
        returns_df
        .select(
            "return_id",
            "order_id",
            "customer_id",
            "product_id",
            "return_date",
            "return_quantity",
            "refund_amount",
            "return_reason",
            "return_status",
            "_ingestion_timestamp",
            "_source_file",
        )
    )


def build_dim_customer(customers_df: DataFrame) -> DataFrame:
    return (
        customers_df
        .select(
            "customer_id",
            "first_name",
            "last_name",
            "email",
            "city",
            "state",
            "country",
            "signup_date",
            "customer_segment",
        )
    )


def build_dim_product(products_df: DataFrame) -> DataFrame:
    return (
        products_df
        .select(
            "product_id",
            "product_name",
            "category",
            "subcategory",
            "brand",
            "unit_price",
            "currency",
        )
    )


def build_dim_date(
    spark,
    start_date: str,
    end_date: str,
) -> DataFrame:
    dates = spark.sql(
        f"""
        SELECT explode(
            sequence(
                to_date('{start_date}'),
                to_date('{end_date}'),
                interval 1 day
            )
        ) AS date
        """
    )

    return (
        dates
        .withColumn("date_key", F.date_format("date", "yyyyMMdd").cast("int"))
        .withColumn("year", F.year("date"))
        .withColumn("quarter", F.quarter("date"))
        .withColumn("month", F.month("date"))
        .withColumn("month_name", F.date_format("date", "MMMM"))
        .withColumn("week_of_year", F.weekofyear("date"))
        .withColumn("day_of_month", F.dayofmonth("date"))
        .withColumn("day_of_week", F.dayofweek("date"))
        .withColumn("day_name", F.date_format("date", "EEEE"))
    )


def merge_by_key(
    spark,
    source_df: DataFrame,
    target_table: str,
    key_columns: list[str],
) -> None:
    if not source_df.take(1):
        return

    if not spark.catalog.tableExists(target_table):
        source_df.write.format("delta").mode("overwrite").saveAsTable(target_table)
        return

    source_df = source_df.dropDuplicates(key_columns)

    target = DeltaTable.forName(spark, target_table)

    merge_condition = " AND ".join(
        [
            f"target.`{column}` = source.`{column}`"
            for column in key_columns
        ]
    )

    (
        target.alias("target")
        .merge(source_df.alias("source"), merge_condition)
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )


def build_customer_sales_summary(orders_df: DataFrame) -> DataFrame:
    return (
        orders_df
        .groupBy("customer_id")
        .agg(
            F.countDistinct("order_id").alias("order_count"),
            F.sum("quantity").alias("units_sold"),
            F.sum("gross_amount").alias("gross_sales_amount"),
            F.sum("discount_amount").alias("discount_amount"),
            F.sum("net_sales_amount").alias("net_sales_amount"),
        )
    )


def build_product_sales_summary(orders_df: DataFrame) -> DataFrame:
    return (
        orders_df
        .groupBy("product_id")
        .agg(
            F.countDistinct("order_id").alias("order_count"),
            F.sum("quantity").alias("units_sold"),
            F.sum("gross_amount").alias("gross_sales_amount"),
            F.sum("discount_amount").alias("discount_amount"),
            F.sum("net_sales_amount").alias("net_sales_amount"),
        )
    )


def build_return_summary(returns_df: DataFrame) -> DataFrame:
    return (
        returns_df
        .groupBy("order_id")
        .agg(
            F.sum("refund_amount").alias("refund_amount"),
            F.sum("return_quantity").alias("returned_units"),
        )
    )


def build_daily_sales_summary(
    orders_df: DataFrame,
    returns_df: DataFrame,
) -> DataFrame:
    return_summary = build_return_summary(returns_df)

    return (
        orders_df
        .join(
            return_summary,
            on="order_id",
            how="left",
        )
        .withColumn(
            "refund_amount",
            F.coalesce(
                F.col("refund_amount"),
                F.lit(0.0),
            ),
        )
        .groupBy("order_date")
        .agg(
            F.countDistinct("order_id").alias("order_count"),
            F.sum("quantity").alias("units_sold"),
            F.sum("gross_amount").alias("gross_sales_amount"),
            F.sum("discount_amount").alias("discount_amount"),
            F.sum("net_sales_amount").alias("net_sales_amount"),
            F.sum("refund_amount").alias("refund_amount"),
        )
        .withColumn(
            "net_revenue",
            F.col("net_sales_amount") - F.col("refund_amount"),
        )
    )


def build_monthly_sales_summary(
    orders_df: DataFrame,
    returns_df: DataFrame,
) -> DataFrame:
    daily_df = build_daily_sales_summary(
        orders_df,
        returns_df,
    )

    return (
        daily_df
        .withColumn("year", F.year("order_date"))
        .withColumn("month", F.month("order_date"))
        .groupBy("year", "month")
        .agg(
            F.sum("order_count").alias("order_count"),
            F.sum("units_sold").alias("units_sold"),
            F.sum("gross_sales_amount").alias("gross_sales_amount"),
            F.sum("discount_amount").alias("discount_amount"),
            F.sum("net_sales_amount").alias("net_sales_amount"),
            F.sum("refund_amount").alias("refund_amount"),
            F.sum("net_revenue").alias("net_revenue"),
        )
    )


def build_customer_revenue_summary(
    orders_df: DataFrame,
    returns_df: DataFrame,
) -> DataFrame:
    return_summary = build_return_summary(returns_df)

    return (
        orders_df
        .join(
            return_summary,
            on="order_id",
            how="left",
        )
        .withColumn(
            "refund_amount",
            F.coalesce(
                F.col("refund_amount"),
                F.lit(0.0),
            ),
        )
        .groupBy("customer_id")
        .agg(
            F.countDistinct("order_id").alias("order_count"),
            F.sum("quantity").alias("units_sold"),
            F.sum("gross_amount").alias("gross_sales_amount"),
            F.sum("discount_amount").alias("discount_amount"),
            F.sum("net_sales_amount").alias("net_sales_amount"),
            F.sum("refund_amount").alias("refund_amount"),
        )
        .withColumn(
            "net_revenue",
            F.col("net_sales_amount") - F.col("refund_amount"),
        )
    )


def build_product_revenue_summary(
    orders_df: DataFrame,
    returns_df: DataFrame,
) -> DataFrame:
    return_summary = (
        returns_df
        .groupBy("order_id", "product_id")
        .agg(
            F.sum("refund_amount").alias("refund_amount"),
            F.sum("return_quantity").alias("returned_units"),
        )
    )

    return (
        orders_df
        .join(
            return_summary,
            on=["order_id", "product_id"],
            how="left",
        )
        .withColumn(
            "refund_amount",
            F.coalesce(
                F.col("refund_amount"),
                F.lit(0.0),
            ),
        )
        .groupBy("product_id")
        .agg(
            F.countDistinct("order_id").alias("order_count"),
            F.sum("quantity").alias("units_sold"),
            F.sum("gross_amount").alias("gross_sales_amount"),
            F.sum("discount_amount").alias("discount_amount"),
            F.sum("net_sales_amount").alias("net_sales_amount"),
            F.sum("refund_amount").alias("refund_amount"),
        )
        .withColumn(
            "net_revenue",
            F.col("net_sales_amount") - F.col("refund_amount"),
        )
    )


def build_promotion_product_summary(
    promotions_df: DataFrame,
    products_df: DataFrame,
) -> DataFrame:
    return (
        promotions_df
        .join(
            products_df.select(
                "product_id",
                "product_name",
                "category",
                "subcategory",
                "brand",
            ),
            on="product_id",
            how="left",
        )
        .select(
            "promotion_id",
            "promotion_name",
            "product_id",
            "product_name",
            "category",
            "subcategory",
            "brand",
            "start_date",
            "end_date",
            "discount_percent",
        )
    )
