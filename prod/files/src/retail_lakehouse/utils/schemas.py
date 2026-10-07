from pyspark.sql.types import (
    DateType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)


CUSTOMER_SCHEMA = StructType([
    StructField("customer_id", StringType(), False),
    StructField("first_name", StringType(), True),
    StructField("last_name", StringType(), True),
    StructField("email", StringType(), True),
    StructField("city", StringType(), True),
    StructField("state", StringType(), True),
    StructField("country", StringType(), True),
    StructField("signup_date", DateType(), True),
    StructField("customer_segment", StringType(), True),
])


PRODUCT_SCHEMA = StructType([
    StructField("product_id", StringType(), False),
    StructField("product_name", StringType(), True),
    StructField("category", StringType(), True),
    StructField("subcategory", StringType(), True),
    StructField("brand", StringType(), True),
    StructField("unit_price", DoubleType(), True),
    StructField("currency", StringType(), True),
])


ORDER_SCHEMA = StructType([
    StructField("order_id", StringType(), False),
    StructField("customer_id", StringType(), True),
    StructField("product_id", StringType(), True),
    StructField("order_date", DateType(), True),
    StructField("quantity", IntegerType(), True),
    StructField("unit_price", DoubleType(), True),
    StructField("discount_amount", DoubleType(), True),
    StructField("payment_method", StringType(), True),
    StructField("order_status", StringType(), True),
])


CLICKSTREAM_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("customer_id", StringType(), True),
    StructField("event_timestamp", TimestampType(), True),
    StructField("event_type", StringType(), True),
    StructField("page_url", StringType(), True),
    StructField("product_id", StringType(), True),
    StructField("device_type", StringType(), True),
    StructField("session_id", StringType(), True),
])


RETURN_SCHEMA = StructType([
    StructField("return_id", StringType(), False),
    StructField("order_id", StringType(), True),
    StructField("customer_id", StringType(), True),
    StructField("product_id", StringType(), True),
    StructField("return_date", DateType(), True),
    StructField("return_quantity", IntegerType(), True),
    StructField("return_reason", StringType(), True),
    StructField("refund_amount", DoubleType(), True),
    StructField("return_status", StringType(), True),
])


PROMOTION_SCHEMA = StructType([
    StructField("promotion_id", StringType(), False),
    StructField("promotion_name", StringType(), True),
    StructField("product_id", StringType(), True),
    StructField("start_date", DateType(), True),
    StructField("end_date", DateType(), True),
    StructField("discount_percent", DoubleType(), True),
    StructField("promotion_type", StringType(), True),
    StructField("status", StringType(), True),
])