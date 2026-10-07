from datetime import datetime, timezone


def generate_batch_id(dataset: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{dataset}_{timestamp}"


def build_raw_path(raw_root: str, dataset_path: str) -> str:
    return f"{raw_root.rstrip('/')}/{dataset_path.lstrip('/')}"