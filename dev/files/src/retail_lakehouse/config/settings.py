from importlib.resources import files

import yaml


CONFIG_ROOT = files("retail_lakehouse").joinpath("config_data")


def load_yaml(file_name: str) -> dict:
    config_file = CONFIG_ROOT.joinpath(file_name)

    with config_file.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def get_environment(environment: str) -> dict:
    config = load_yaml("environments.yml")

    if environment not in config["environments"]:
        raise ValueError(f"Unknown environment: {environment}")

    return config["environments"][environment]


def get_datasets() -> dict:
    config = load_yaml("datasets.yml")
    return config["datasets"]