"""Azure cloud OCR.

Two providers are supported:

- azure_read:     Azure AI Vision Read API v3.2 (the original setup).
- azure_docintel: Azure AI Document Intelligence prebuilt-read model.
                  Microsoft's language list for this model includes Greek
                  printed text, while the Vision Read list does not. Use it if
                  Greek print accuracy is poor with azure_read. It needs an
                  Azure AI services (multi-service) or Document Intelligence
                  resource.

Neither provider supports Greek handwriting; see vlm_ocr.py for that.
"""
import logging
import os
import time
from typing import Any, Dict, Optional

import cv2
import requests

from app.vision.types import OcrResult

logger = logging.getLogger(__name__)

PROVIDERS = ("azure_read", "azure_docintel")


class AzureReadOcr:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.enabled = bool(config.get("enabled", False))
        self.provider = config.get("provider", "azure_read")
        if self.provider not in PROVIDERS:
            logger.warning("Unknown cloud_ocr.provider %r, using azure_read", self.provider)
            self.provider = "azure_read"
        self.endpoint = config.get("endpoint") or os.getenv("AZURE_CV_ENDPOINT", "")
        self.key = config.get("key") or os.getenv("AZURE_CV_KEY", "")
        self.language = config.get("language", "")
        self.reading_order = config.get("reading_order", "natural")
        self.docintel_api_version = config.get("docintel_api_version", "2024-11-30")
        self.timeout = float(config.get("timeout_seconds", 10))
        self.poll_interval = float(config.get("poll_interval_seconds", 0.4))

    def is_configured(self) -> bool:
        return self.enabled and bool(self.endpoint) and bool(self.key)

    # ------------------------------------------------------------------ run
    def run(self, image) -> Optional[OcrResult]:
        if not self.is_configured():
            logger.debug("Cloud OCR not configured, skipping")
            return None
        payload = encode_jpeg(image)
        if payload is None:
            logger.error("Failed to encode image for cloud OCR")
            return None

        headers = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Content-Type": "application/octet-stream",
        }
        try:
            response = requests.post(
                self._build_url(), headers=headers, data=payload, timeout=self.timeout
            )
        except requests.RequestException as exc:
            logger.error("Cloud OCR request failed: %s", exc)
            return None

        if response.status_code >= 300:
            logger.error(
                "Cloud OCR returned HTTP %d: %s", response.status_code, response.text[:200]
            )
            return None

        operation_url = response.headers.get("Operation-Location")
        if not operation_url:
            logger.error("Cloud OCR response missing Operation-Location header")
            return None

        data = self._poll(operation_url)
        if data is None:
            return None
        if self.provider == "azure_docintel":
            return parse_docintel_result(data)
        return parse_read_result(data)

    def _poll(self, operation_url: str) -> Optional[Dict[str, Any]]:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                poll = requests.get(
                    operation_url,
                    headers={"Ocp-Apim-Subscription-Key": self.key},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                logger.error("Cloud OCR poll failed: %s", exc)
                return None
            if poll.status_code >= 300:
                logger.error("Cloud OCR poll returned HTTP %d", poll.status_code)
                return None
            data = poll.json()
            status = str(data.get("status", "")).lower()
            if status == "succeeded":
                return data
            if status == "failed":
                logger.error("Cloud OCR operation failed: %s", str(data)[:300])
                return None
            time.sleep(self.poll_interval)
        logger.error("Cloud OCR timed out after %.1fs", self.timeout)
        return None

    def _build_url(self) -> str:
        base = self.endpoint.rstrip("/")
        if self.provider == "azure_docintel":
            return (
                f"{base}/documentintelligence/documentModels/prebuilt-read:analyze"
                f"?api-version={self.docintel_api_version}"
            )
        params = f"readingOrder={self.reading_order}"
        if self.language:
            params = f"language={self.language}&{params}"
        return f"{base}/vision/v3.2/read/analyze?{params}"


# ---------------------------------------------------------------- helpers
_MAX_BYTES = 4 * 1024 * 1024  # Azure 4 MB upload limit


def encode_jpeg(image, max_bytes: int = _MAX_BYTES, max_side: int = 0) -> Optional[bytes]:
    """JPEG-encode an OpenCV image, shrinking it until it fits max_bytes."""
    if max_side:
        h, w = image.shape[:2]
        scale = max_side / float(max(h, w))
        if scale < 1.0:
            image = cv2.resize(
                image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA
            )
    for _ in range(3):
        for quality in (90, 75, 60):
            ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if not ok:
                return None
            if len(buf) <= max_bytes:
                return buf.tobytes()
        h, w = image.shape[:2]
        image = cv2.resize(image, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    return None


def _to_percent(value: float) -> float:
    return value * 100.0 if value <= 1.0 else value


def parse_read_result(data: Dict[str, Any]) -> OcrResult:
    """Parse an Azure AI Vision Read v3.2 result."""
    analyze = data.get("analyzeResult", {})
    lines, confidences = [], []
    handwriting = False
    for page in analyze.get("readResults", []):
        for line in page.get("lines", []):
            text = line.get("text", "")
            if text:
                lines.append(text)
            words = line.get("words", [])
            word_conf = [float(w["confidence"]) for w in words if "confidence" in w]
            if word_conf:
                confidences.extend(word_conf)
            elif "confidence" in line:
                confidences.append(float(line["confidence"]))
            style = line.get("appearance", {}).get("style", {})
            if style.get("name") == "handwriting":
                handwriting = True
    merged = "\n".join(lines).strip()
    conf = sum(confidences) / len(confidences) if confidences else (90.0 if merged else 0.0)
    result = OcrResult(merged, _to_percent(conf), handwriting, "azure_read")
    logger.info(
        "Azure Read: %d lines, conf=%.1f, handwriting=%s", len(lines), result.confidence, handwriting
    )
    return result


def parse_docintel_result(data: Dict[str, Any]) -> OcrResult:
    """Parse an Azure Document Intelligence prebuilt-read result."""
    analyze = data.get("analyzeResult", {})
    lines, confidences = [], []
    for page in analyze.get("pages", []):
        for line in page.get("lines", []):
            text = line.get("content", "")
            if text:
                lines.append(text)
        for word in page.get("words", []):
            if "confidence" in word:
                confidences.append(float(word["confidence"]))
    handwriting = any(
        style.get("isHandwritten") and float(style.get("confidence", 1.0)) >= 0.5
        for style in analyze.get("styles", [])
    )
    merged = "\n".join(lines).strip()
    conf = sum(confidences) / len(confidences) if confidences else (90.0 if merged else 0.0)
    result = OcrResult(merged, _to_percent(conf), handwriting, "azure_docintel")
    logger.info(
        "Document Intelligence: %d lines, conf=%.1f, handwriting=%s",
        len(lines),
        result.confidence,
        handwriting,
    )
    return result
