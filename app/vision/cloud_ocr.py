import os
import time
from typing import Any, Dict, Optional, Tuple

import cv2
import requests


class AzureReadOcr:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.enabled = bool(config.get("enabled", False))
        self.endpoint = config.get("endpoint") or os.getenv("AZURE_CV_ENDPOINT", "")
        self.key = config.get("key") or os.getenv("AZURE_CV_KEY", "")
        self.language = config.get("language", "en")
        self.reading_order = config.get("reading_order", "basic")
        self.timeout = float(config.get("timeout_seconds", 15))
        self.poll_interval = float(config.get("poll_interval_seconds", 0.5))

    def is_configured(self) -> bool:
        return self.enabled and bool(self.endpoint) and bool(self.key)

    def run(self, image) -> Optional[Tuple[str, float]]:
        if not self.is_configured():
            return None
        url = self._build_url()
        payload = self._encode_image(image)
        if payload is None:
            return None

        headers = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Content-Type": "application/octet-stream",
        }
        response = requests.post(url, headers=headers, data=payload, timeout=self.timeout)
        if response.status_code >= 300:
            return None

        operation_url = response.headers.get("Operation-Location")
        if not operation_url:
            return None

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            poll = requests.get(
                operation_url,
                headers={"Ocp-Apim-Subscription-Key": self.key},
                timeout=self.timeout,
            )
            if poll.status_code >= 300:
                return None
            data = poll.json()
            status = data.get("status", "").lower()
            if status == "succeeded":
                return self._parse_result(data)
            if status == "failed":
                return None
            time.sleep(self.poll_interval)
        return None

    def _build_url(self) -> str:
        base = self.endpoint.rstrip("/")
        return (
            f"{base}/vision/v3.2/read/analyze"
            f"?language={self.language}&readingOrder={self.reading_order}"
        )

    def _encode_image(self, image) -> Optional[bytes]:
        ok, buf = cv2.imencode(".jpg", image)
        if not ok:
            return None
        return buf.tobytes()

    def _parse_result(self, data: Dict[str, Any]) -> Tuple[str, float]:
        analyze = data.get("analyzeResult", {})
        read_results = analyze.get("readResults", [])
        lines = []
        confidences = []
        for block in read_results:
            for line in block.get("lines", []):
                text = line.get("text", "")
                if text:
                    lines.append(text)
                if "confidence" in line:
                    confidences.append(float(line["confidence"]))
        merged = " ".join(lines).strip()
        if confidences:
            avg_conf = sum(confidences) / len(confidences)
        else:
            avg_conf = 0.9 if merged else 0.0
        return merged, avg_conf
