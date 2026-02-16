import logging
import os
import cv2

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

from app.config import load_config
from app.vision.pipeline import VisionPipeline

config = load_config("config.yaml")
print("cloud_ocr.enabled:", config.get("cloud_ocr", {}).get("enabled"))
print("cloud_ocr.primary:", config.get("cloud_ocr", {}).get("primary"))
print("cloud_ocr.key set:", bool(config.get("cloud_ocr", {}).get("key")))
print("AZURE_CV_KEY env:", bool(os.getenv("AZURE_CV_KEY")))
print("AZURE_SPEECH_KEY env:", bool(os.getenv("AZURE_SPEECH_KEY")))
print("tts.azure_enabled:", config.get("tts", {}).get("azure_enabled"))

pipeline = VisionPipeline(config)
print("cloud.is_configured:", pipeline.cloud.is_configured())
print("cloud_primary:", pipeline.cloud_primary)

image = cv2.imread("test1.JPG")
result = pipeline.process(image, skip_quality=True)
print("Status:", result.status)
print("Confidence:", result.confidence)
print("Text:", result.text)
