from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np

from app.vision.cloud_ocr import AzureReadOcr
from app.vision.ocr import OcrEngine
from app.vision.quality import QualityChecker
from app.vision.text_detector import Box, TextDetector


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

    def process(self, image: np.ndarray, skip_quality: bool = False) -> VisionResult:
        if skip_quality:
            ok, reason = True, "ok"
        else:
            ok, reason = self.quality.check(image)
        if not ok:
            return VisionResult(status="bad_quality", reason=reason)

        boxes = self.detector.detect(image)
        if boxes:
            text, confidence = self._ocr_regions(image, boxes)
        else:
            text, confidence = self.ocr.run(image)

        if self.cloud.is_configured() and (
            not text or confidence < self.cloud_trigger_conf
        ):
            cloud_result = self.cloud.run(image)
            if cloud_result:
                text, confidence = cloud_result

        if not text:
            return VisionResult(status="no_text")

        return VisionResult(status="ok", text=text, confidence=confidence)

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
