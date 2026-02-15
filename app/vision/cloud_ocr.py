import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import cv2
import requests

logger = logging.getLogger(__name__)


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
            logger.debug("Azure Read OCR not configured, skipping")
            return None
        url = self._build_url()
        payload = self._encode_image(image)
        if payload is None:
            logger.error("Failed to encode image for Azure Read API")
            return None

        headers = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Content-Type": "application/octet-stream",
        }
        try:
            response = requests.post(url, headers=headers, data=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            logger.error("Azure Read API request failed: %s", exc)
            return None

        if response.status_code >= 300:
            logger.error(
                "Azure Read API returned HTTP %d: %s",
                response.status_code,
                response.text[:200],
            )
            return None

        operation_url = response.headers.get("Operation-Location")
        if not operation_url:
            logger.error("Azure response missing Operation-Location header")
            return None

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                poll = requests.get(
                    operation_url,
                    headers={"Ocp-Apim-Subscription-Key": self.key},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                logger.error("Azure poll request failed: %s", exc)
                return None

            if poll.status_code >= 300:
                logger.error("Azure poll returned HTTP %d", poll.status_code)
                return None
            data = poll.json()
            status = data.get("status", "").lower()
            if status == "succeeded":
                return self._parse_result(data)
            if status == "failed":
                logger.error("Azure Read operation failed: %s", data)
                return None
            time.sleep(self.poll_interval)

        logger.error("Azure Read API timed out after %.1fs", self.timeout)
        return None

    def _build_url(self) -> str:
        base = self.endpoint.rstrip("/")
        params = f"readingOrder={self.reading_order}"
        if self.language:
            params = f"language={self.language}&{params}"
        return f"{base}/vision/v3.2/read/analyze?{params}"

    _MAX_BYTES = 4 * 1024 * 1024  # Azure 4 MB limit

    def _encode_image(self, image) -> Optional[bytes]:
        # Start with quality 90, reduce if needed to stay under 4 MB
        for quality in (90, 75, 60):
            ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if not ok:
                return None
            data = buf.tobytes()
            if len(data) <= self._MAX_BYTES:
                return data
        # Still too large — downscale by half and try once more
        h, w = image.shape[:2]
        small = cv2.resize(image, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return None
        return buf.tobytes()

    def _parse_result(self, data: Dict[str, Any]) -> Tuple[str, float]:
        analyze = data.get("analyzeResult", {})
        read_results = analyze.get("readResults", [])
        lines = []
        confidences = []
        has_handwriting = False
        for block in read_results:
            for line in block.get("lines", []):
                text = line.get("text", "")
                if text:
                    lines.append(text)
                if "confidence" in line:
                    confidences.append(float(line["confidence"]))
                # Azure may include appearance/style info for handwriting
                appearance = line.get("appearance", {})
                style = appearance.get("style", {})
                if style.get("name") == "handwriting":
                    has_handwriting = True
        if has_handwriting:
            logger.info("Azure detected handwriting in the image")
        merged = " ".join(lines).strip()
        if confidences:
            avg_conf = sum(confidences) / len(confidences)
        else:
            avg_conf = 0.9 if merged else 0.0
        # Azure returns 0-1 confidence; normalize to 0-100 to match local OCR
        if avg_conf <= 1.0:
            avg_conf *= 100.0
        logger.info("Azure result: %d lines, avg_conf=%.2f", len(lines), avg_conf)
        return merged, avg_conf
