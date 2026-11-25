"""Run the OCR pipeline on one image and print what each stage decided.

Usage (from the repo root):  python3 tools/debug_pipeline.py photo.jpg
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2  # noqa: E402

from app.config import load_config  # noqa: E402
from app.vision.pipeline import VisionPipeline  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

path = sys.argv[1] if len(sys.argv) > 1 else "test1.JPG"
config = load_config("config.yaml")
pipeline = VisionPipeline(config)
print("cloud configured:", pipeline.cloud.is_configured(), "provider:", pipeline.cloud.provider)
print("vlm configured:  ", pipeline.vlm.is_configured(), "provider:", pipeline.vlm.provider)
print("AZURE_CV_KEY set:", bool(os.getenv("AZURE_CV_KEY")))

image = cv2.imread(path)
if image is None:
    sys.exit(f"Cannot read {path}")
result = pipeline.process(image, skip_quality=True)
print("Status:    ", result.status)
print("Source:    ", result.source)
print("Confidence:", round(result.confidence, 1))
print("Text:\n", result.text)
