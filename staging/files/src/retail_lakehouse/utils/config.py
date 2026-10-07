from importlib.resources import files
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOCAL_CONFIG_ROOT = PROJECT_ROOT / "config"


def load_config(filename: str) -> dict:
    local_config_path = LOCAL_CONFIG_ROOT / filename

    if local_config_path.exists():
        with local_config_path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    packaged_config = files("retail_lakehouse").joinpath(
        "config_data",
        filename,
    )

    if not packaged_config.is_file():
        raise FileNotFoundError(
            f"Configuration file not found locally or in package: {filename}"
        )

    with packaged_config.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)