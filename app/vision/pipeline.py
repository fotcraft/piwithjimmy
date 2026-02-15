import logging
from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np

from app.vision.cloud_ocr import AzureReadOcr
from app.vision.ocr import OcrEngine
from app.vision.quality import QualityChecker
from app.vision.text_detector import Box, TextDetector

logger = logging.getLogger(__name__)


@dataclass
class VisionResult:
    status: str
    text: str = ""
    confidence: float = 0.0
    reason: str = ""


class VisionPipeline:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.quality = QualityChecker(config.get("quality", {}))
        self.detector = TextDetector(config.get("vision", {}))
        self.ocr = OcrEngine(config.get("ocr", {}))
        self.cloud = AzureReadOcr(config.get("cloud_ocr", {}))
        self.cloud_trigger_conf = float(
            config.get("cloud_ocr", {}).get("trigger_confidence", 40.0)
        )
        self.cloud_primary = bool(
            config.get("cloud_ocr", {}).get("primary", False)
        )

    def process(self, image: np.ndarray, skip_quality: bool = False) -> VisionResult:
        if skip_quality:
            ok, reason = True, "ok"
        else:
            ok, reason = self.quality.check(image)
        if not ok:
            return VisionResult(status="bad_quality", reason=reason)

        if self.cloud_primary and self.cloud.is_configured():
            return self._process_cloud_first(image)

        return self._process_local_first(image)

    def _process_cloud_first(self, image: np.ndarray) -> VisionResult:
        """Azure first: skip local OCR entirely if Azure succeeds."""
        logger.info("Cloud-primary mode: calling Azure Read API")
        cloud_result = self.cloud.run(image)
        if cloud_result:
            text, confidence = cloud_result
            if text:
                logger.info("Azure succeeded (confidence=%.1f)", confidence)
                return VisionResult(status="ok", text=text, confidence=confidence)

        # Azure failed or returned no text — fall back to local OCR
        logger.warning("Azure returned no text, falling back to local OCR")
        return self._run_local_ocr(image)

    def _process_local_first(self, image: np.ndarray) -> VisionResult:
        """Original behaviour: local OCR first, Azure as fallback."""
        text, confidence = self._run_local_ocr_raw(image)

        if self.cloud.is_configured() and (
            not text or confidence < self.cloud_trigger_conf
        ):
            cloud_result = self.cloud.run(image)
            if cloud_result:
                text, confidence = cloud_result

        if not text:
            return VisionResult(status="no_text")
        return VisionResult(status="ok", text=text, confidence=confidence)

    def _run_local_ocr(self, image: np.ndarray) -> VisionResult:
        text, confidence = self._run_local_ocr_raw(image)
        if not text:
            return VisionResult(status="no_text")
        return VisionResult(status="ok", text=text, confidence=confidence)

    def _run_local_ocr_raw(self, image: np.ndarray) -> tuple[str, float]:
        boxes = self.detector.detect(image)
        if boxes:
            return self._ocr_regions(image, boxes)
        return self.ocr.run(image)

    def _ocr_regions(self, image: np.ndarray, boxes: List[Box]) -> tuple[str, float]:
        texts: List[str] = []
        confidences: List[float] = []
        for x, y, w, h in boxes:
            crop = image[y : y + h, x : x + w]
            text, conf = self.ocr.run(crop)
            if text:
                texts.append(text)
                confidences.append(conf)
        if not texts:
            return "", 0.0
        merged = " ".join(texts).strip()
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return merged, avg_conf
