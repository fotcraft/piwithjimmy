import json
import os
import time
from typing import Any, Dict, Optional


class LastResultStore:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.path = config.get("last_result_path", "data/last_result.json")

    def save(self, text: str, lang: str) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        payload = {
            "text": text,
            "lang": lang,
            "timestamp": int(time.time()),
        }
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)

    def load(self) -> Optional[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return None
        with open(self.path, "r", encoding="utf-8") as handle:
            return json.load(handle)
