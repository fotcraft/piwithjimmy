from typing import Any, Dict, List, Tuple

import numpy as np


Box = Tuple[int, int, int, int]


class TextDetector:
    """
    Edge TPU text detector stub.
    Replace with a TFLite Edge TPU model and inference logic.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

    def detect(self, image: np.ndarray) -> List[Box]:
        _ = image
        return []
