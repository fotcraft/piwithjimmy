from typing import Any, Dict, Tuple

import cv2
import numpy as np


class QualityChecker:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.enabled = bool(config.get("enabled", True))
        self.blur_threshold = float(config.get("blur_threshold", 120.0))
        self.min_brightness = float(config.get("min_brightness", 60.0))
        self.max_brightness = float(config.get("max_brightness", 200.0))

    def check(self, image: np.ndarray) -> Tuple[bool, str]:
        if not self.enabled:
            return True, "ok"
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        if blur_score < self.blur_threshold:
            return False, "blur"

        brightness = float(np.mean(gray))
        if brightness < self.min_brightness:
            return False, "dark"
        if brightness > self.max_brightness:
            return False, "bright"

        return True, "ok"
