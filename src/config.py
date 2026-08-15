import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

pbf_file = ""
pbf_viewport = {}
default_start = []
default_target = []


def read_city_config(config_path: str | os.PathLike | None = None):
    """Read a city config JSON file and populate routing defaults."""
    global pbf_file, pbf_viewport, default_start, default_target

    config_file = Path(config_path) if config_path is not None else BASE_DIR / "osm_data" / "city_config.json"
    if not config_file.is_absolute():
        config_file = BASE_DIR / config_file

    if not config_file.exists():
        raise FileNotFoundError(f"Config file '{config_file}' not found.")

    with config_file.open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    required_fields = ["default_start", "default_target", "pbf_viewport", "filename"]
    missing_fields = [field for field in required_fields if field not in config]
    if missing_fields:
        raise KeyError(f"Config file '{config_file}' is missing required fields: {missing_fields}")

    pbf_viewport = config["pbf_viewport"]
    default_start = config["default_start"]
    default_target = config["default_target"]

    filename = config["filename"]
    pbf_path = Path(filename)
    if not pbf_path.is_absolute():
        pbf_path = BASE_DIR / pbf_path
    pbf_file = str(pbf_path)

    return {
        "filename": pbf_file,
        "default_start": default_start,
        "default_target": default_target,
        "pbf_viewport": pbf_viewport,
    }


read_city_config()
