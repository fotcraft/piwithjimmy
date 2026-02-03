import os
from typing import Any, Dict

import yaml


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    _ensure_storage_dir(config)
    return config


def _ensure_storage_dir(config: Dict[str, Any]) -> None:
    storage = config.get("storage", {})
    last_path = storage.get("last_result_path")
    if not last_path:
        return
    directory = os.path.dirname(last_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
