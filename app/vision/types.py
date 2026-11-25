from dataclasses import dataclass


@dataclass
class OcrResult:
    """Text recognised by one OCR engine.

    confidence is on a 0-100 scale for every engine.
    handwriting is True when the engine reports handwritten text.
    source names the engine, for logs and the benchmark tool.
    """

    text: str
    confidence: float
    handwriting: bool = False
    source: str = ""
