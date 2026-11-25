"""Image -> text pipeline.

Order of engines (cloud_ocr.primary: true, the default):

1. Image quality check (blur / exposure).
2. Azure OCR (Read or Document Intelligence), if the network is reachable.
3. Vision-language model, if Azure found handwriting, low confidence or no
   text. This is what reads Greek handwriting.
4. Local Tesseract (Greek + English print), if the cloud is unreachable or
   returned nothing.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from app import net
from app.vision.cloud_ocr import AzureReadOcr
from app.vision.ocr import OcrEngine
from app.vision.quality import QualityChecker
from app.vision.text_detector import Box, TextDetector
from app.vision.types import OcrResult
from app.vision.vlm_ocr import VlmOcr

logger = logging.getLogger(__name__)


@dataclass
class VisionResult:
    status: str  # ok | bad_quality | no_text | error
    text: str = ""
    confidence: float = 0.0
    reason: str = ""
    source: str = ""


class VisionPipeline:
    def __init__(
        self,
        config: Dict[str, Any],
        cloud: Optional[AzureReadOcr] = None,
        vlm: Optional[VlmOcr] = None,
        local: Optional[OcrEngine] = None,
        quality: Optional[QualityChecker] = None,
    ) -> None:
        cloud_cfg = config.get("cloud_ocr", {})
        vlm_cfg = config.get("vlm", {})
        self.quality = quality or QualityChecker(config.get("quality", {}))
        self.detector = TextDetector(config.get("vision", {}))
        self.ocr = local or OcrEngine(config.get("ocr", {}))
        self.cloud = cloud or AzureReadOcr(cloud_cfg)
        self.vlm = vlm or VlmOcr(vlm_cfg)
        self.cloud_primary = bool(cloud_cfg.get("primary", True))
        self.cloud_trigger_conf = float(cloud_cfg.get("trigger_confidence", 40.0))
        self.vlm_trigger_conf = float(vlm_cfg.get("trigger_confidence", 70.0))
        self.vlm_on_handwriting = bool(vlm_cfg.get("on_handwriting", True))
        self.check_network = bool(config.get("network", {}).get("check_before_cloud", True))

    # ----------------------------------------------------------------- api
    def process(
        self, image: np.ndarray, skip_quality: bool = False, lang_hint: str = "auto"
    ) -> VisionResult:
        if not skip_quality:
            ok, reason = self.quality.check(image)
            if not ok:
                return VisionResult(status="bad_quality", reason=reason)

        try:
            if self.cloud_primary:
                result = self._cloud_first(image, lang_hint)
            else:
                result = self._local_first(image, lang_hint)
        except Exception as exc:  # never crash the device on a bad scan
            logger.exception("Vision pipeline error: %s", exc)
            return VisionResult(status="error", reason=str(exc))

        if result is None or not result.text:
            return VisionResult(status="no_text")
        return VisionResult(
            status="ok", text=result.text, confidence=result.confidence, source=result.source
        )

    # ------------------------------------------------------------- routing
    def _cloud_first(self, image, lang_hint: str) -> Optional[OcrResult]:
        cloud_res = None
        if self._online(self.cloud):
            cloud_res = self.cloud.run(image)
        if self._needs_vlm(cloud_res, lang_hint) and self._online(self.vlm):
            vlm_res = self.vlm.run(image)
            if vlm_res and vlm_res.text:
                return vlm_res
        if cloud_res and cloud_res.text:
            return cloud_res
        logger.info("Cloud unavailable or empty, using local OCR")
        return self._run_local(image)

    def _local_first(self, image, lang_hint: str) -> Optional[OcrResult]:
        local_res = self._run_local(image)
        if local_res and local_res.text and local_res.confidence >= self.cloud_trigger_conf:
            return local_res
        cloud_res = self._cloud_first(image, lang_hint) if self._any_cloud() else None
        if cloud_res and cloud_res.text:
            return cloud_res
        return local_res

    def _needs_vlm(self, res: Optional[OcrResult], lang_hint: str) -> bool:
        if not self.vlm.is_configured():
            return False
        if res is None or not res.text:
            return True
        if res.confidence < self.vlm_trigger_conf:
            return True
        # Azure reads English handwriting itself; anything else goes to the VLM.
        return self.vlm_on_handwriting and res.handwriting and lang_hint != "en"

    def _any_cloud(self) -> bool:
        return self.cloud.is_configured() or self.vlm.is_configured()

    def _online(self, engine) -> bool:
        if not engine.is_configured():
            return False
        if not self.check_network:
            return True
        url = engine.endpoint if hasattr(engine, "endpoint") and engine.endpoint else engine.base_url()
        ok = net.is_reachable(url)
        if not ok:
            logger.warning("Network unreachable for %s", url)
        return ok

    # --------------------------------------------------------------- local
    def _run_local(self, image) -> Optional[OcrResult]:
        boxes = self.detector.detect(image)
        if boxes:
            text, conf = self._ocr_regions(image, boxes)
        else:
            text, conf = self.ocr.run(image)
        return OcrResult(text, conf, False, f"local_{self.ocr.backend}")

    def _ocr_regions(self, image: np.ndarray, boxes: List[Box]) -> tuple:
        texts: List[str] = []
        confidences: List[float] = []
        for x, y, w, h in boxes:
            text, conf = self.ocr.run(image[y : y + h, x : x + w])
            if text:
                texts.append(text)
                confidences.append(conf)
        if not texts:
            return "", 0.0
        return " ".join(texts).strip(), sum(confidences) / len(confidences)
