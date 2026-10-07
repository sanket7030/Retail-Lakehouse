from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def _is_null_or_empty(column_name: str):
    column = F.col(column_name)

    if column_name not in column_name:
        raise ValueError(f"Column '{column_name}' does not exist")

    return column.isNull() | (F.trim(column.cast("string")) == "")


def _build_rule_condition(df: DataFrame, rule: dict):
    column_name = rule["column"]

    if column_name not in df.columns:
        raise ValueError(
            f"Validation rule references missing column '{column_name}'"
        )

    column = F.col(column_name)
    rule_type = rule["rule"]

    if rule_type == "regex":
        return ~column.cast("string").rlike(rule["pattern"])

    if rule_type == "not_empty":
        return column.isNull() | (F.trim(column.cast("string")) == "")

    if rule_type == "greater_than":
        return column <= F.lit(rule["value"])

    if rule_type == "greater_than_or_equal":
        return column < F.lit(rule["value"])

    if rule_type == "less_than":
        return column >= F.lit(rule["value"])

    if rule_type == "less_than_or_equal":
        return column > F.lit(rule["value"])

    if rule_type == "column_greater_than_or_equal":
        compare_to = rule["compare_to"]

        if compare_to not in df.columns:
            raise ValueError(
                f"Validation rule references missing comparison column "
                f"'{compare_to}'"
            )

        return column < F.col(compare_to)

    raise ValueError(
        f"Unsupported validation rule '{rule_type}'"
    )


def add_quality_columns(
    df: DataFrame,
    required_columns: list[str],
    validation_rules: list[dict] | None = None,
) -> DataFrame:

    validation_rules = validation_rules or []

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Required columns missing from DataFrame: {missing_columns}"
        )

    failure_reason_columns = []

    for column_name in required_columns:
        failure_reason_columns.append(
            F.when(
                F.col(column_name).isNull()
                | (F.trim(F.col(column_name).cast("string")) == ""),
                F.lit(f"{column_name} is null or empty"),
            )
        )

    for rule in validation_rules:
        condition = _build_rule_condition(df, rule)

        failure_reason_columns.append(
            F.when(
                condition,
                F.lit(rule["reason"]),
            )
        )

    reason_array = F.array(*failure_reason_columns)

    reason_array = F.filter(
        reason_array,
        lambda reason: reason.isNotNull(),
    )

    return (
        df.withColumn(
            "_quality_reason",
            F.when(
                F.size(reason_array) > 0,
                F.concat_ws("; ", reason_array),
            ).otherwise(F.lit(None).cast("string")),
        )
        .withColumn(
            "_quality_status",
            F.when(
                F.size(reason_array) > 0,
                F.lit("QUARANTINE"),
            ).otherwise(F.lit("VALID")),
        )
    )