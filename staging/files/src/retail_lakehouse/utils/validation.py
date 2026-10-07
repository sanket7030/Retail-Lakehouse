from pyspark.sql import DataFrame


def validate_required_columns(
    df: DataFrame,
    required_columns: list[str],
) -> None:
    actual_columns = set(df.columns)
    missing_columns = set(required_columns) - actual_columns

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {sorted(missing_columns)}"
        )


def validate_not_empty(df: DataFrame) -> None:
    if df.limit(1).count() == 0:
        raise ValueError("DataFrame is empty")