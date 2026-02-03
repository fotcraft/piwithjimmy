import os
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
import pytesseract


class OcrEngine:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.backend = config.get("backend", "tesseract")
        self.langs = config.get("tesseract_langs", "ell+eng")
        self.preprocess = bool(config.get("preprocess", False))
        self.scale = float(config.get("scale", 1.6))
        self.easyocr_langs: List[str] = list(config.get("easyocr_langs", ["en"]))
        self.paddle_langs: List[str] = list(config.get("paddle_langs", ["en"]))
        self.paddle_use_angle_cls = bool(config.get("paddle_use_angle_cls", True))
        self.paddle_show_log = bool(config.get("paddle_show_log", False))
        self._paddle_instances: Dict[str, Any] = {}
        self._easyocr_instances: Dict[str, Any] = {}

    def run(self, image) -> Tuple[str, float]:
        if self.backend == "easyocr":
            return self._run_easyocr(image)
        if self.backend == "paddleocr":
            return self._run_paddle(image)
        return self._run_tesseract(image)

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        if not self.preprocess:
            return image
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if self.scale and self.scale != 1.0:
            gray = cv2.resize(
                gray,
                None,
                fx=self.scale,
                fy=self.scale,
                interpolation=cv2.INTER_CUBIC,
            )
        thresh = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            10,
        )
        return thresh

    def _run_tesseract(self, image) -> Tuple[str, float]:
        image = self._preprocess(image)
        data = pytesseract.image_to_data(
            image, lang=self.langs, output_type=pytesseract.Output.DICT
        )
        text = " ".join(word for word in data.get("text", []) if word).strip()
        confidences = [
            float(c)
            for c in data.get("conf", [])
            if c not in ("-1", -1, None) and float(c) >= 0
        ]
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return text, confidence

    def _run_paddle(self, image) -> Tuple[str, float]:
        if not self.paddle_langs:
            self.paddle_langs = ["en"]
        if len(self.paddle_langs) == 1:
            return self._run_paddle_lang(image, self.paddle_langs[0])

        best_text = ""
        best_conf = 0.0
        for lang in self.paddle_langs:
            text, conf = self._run_paddle_lang(image, lang)
            if conf > best_conf:
                best_text, best_conf = text, conf
        return best_text, best_conf

    def _run_paddle_lang(self, image, lang: str) -> Tuple[str, float]:
        ocr = self._get_paddle(lang)
        try:
            result = ocr.ocr(image, cls=self.paddle_use_angle_cls)
        except TypeError:
            result = ocr.ocr(image)
        if not result:
            return "", 0.0

        lines: List[str] = []
        confidences: List[float] = []
        for item in result:
            for line in item:
                if len(line) >= 2 and line[1]:
                    text, conf = line[1]
                    if text:
                        lines.append(text)
                        confidences.append(float(conf))
        merged = " ".join(lines).strip()
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return merged, avg_conf

    def _get_paddle(self, lang: str):
        if lang in self._paddle_instances:
            return self._paddle_instances[lang]
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        try:
            from paddleocr import PaddleOCR
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "paddleocr not installed. Install paddleocr and paddlepaddle."
            ) from exc
        base_kwargs = {
            "use_angle_cls": self.paddle_use_angle_cls,
            "lang": lang,
        }
        try:
            instance = PaddleOCR(show_log=self.paddle_show_log, **base_kwargs)
        except (TypeError, ValueError):
            instance = PaddleOCR(**base_kwargs)
        self._paddle_instances[lang] = instance
        return instance

    def _run_easyocr(self, image) -> Tuple[str, float]:
        if not self.easyocr_langs:
            self.easyocr_langs = ["en"]
        reader = self._get_easyocr(self.easyocr_langs)
        result = reader.readtext(image)
        if not result:
            return "", 0.0
        lines: List[str] = []
        confidences: List[float] = []
        for _, text, conf in result:
            if text:
                lines.append(text)
                confidences.append(float(conf))
        merged = " ".join(lines).strip()
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return merged, avg_conf

    def _get_easyocr(self, langs: List[str]):
        key = ",".join(langs)
        if key in self._easyocr_instances:
            return self._easyocr_instances[key]
        try:
            import easyocr
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("easyocr not installed. Install easyocr and torch.") from exc
        reader = easyocr.Reader(langs, gpu=False)
        self._easyocr_instances[key] = reader
        return reader
