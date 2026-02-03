MVP Reader (Pi 5 + Coral TPU)

Offline, on-device text reading for Raspberry Pi 5 with Coral Edge TPU acceleration
for text detection. OCR and TTS run on the Pi CPU.

Features (MVP scaffold)
- Scan/Repeat/Volume/Language buttons (hardware stubs included)
- Camera capture via picamera2
- Image quality checks (blur/exposure)
- TPU text-region detection stub (drop-in for Edge TPU model)
- OCR via tesseract-ocr
- TTS via espeak-ng
- Greek/English language detection and normalization
- Last-result storage for Repeat

Quick start (Pi 5)
1) Install system dependencies:
   - sudo apt-get update
   - sudo apt-get install -y python3-picamera2 python3-opencv tesseract-ocr espeak-ng

2) (Optional) Install Edge TPU runtime:
   - https://coral.ai/docs/accelerator/get-started/

3) Python deps:
   - python3 -m venv .venv
   - source .venv/bin/activate
   - pip install --upgrade pip
   - pip install -r requirements.txt

4) For advanced OCR, choose one:
   - PaddleOCR (fast, but can be unstable on some Pi builds):
     - pip install paddlepaddle
   - EasyOCR (more stable, heavier):
     - pip install torch torchvision
     - pip install easyocr

5) Optional cloud OCR (Azure Read):
   - Create an Azure Computer Vision resource
   - Set `cloud_ocr.enabled: true` in config.yaml
   - Fill `cloud_ocr.endpoint` and `cloud_ocr.key`
   - Or export environment variables:
     - AZURE_CV_ENDPOINT
     - AZURE_CV_KEY

5) Run:
   - python3 main.py --config config.yaml

Testing without a camera
- python3 main.py --image /path/to/test.jpg

Notes
- Hardware GPIO wiring is stubbed. Replace `app/hal/buttons.py` and
  `app/hal/leds.py` with your actual GPIO logic.
- TPU text detection is stubbed in `app/vision/text_detector.py`.
  Plug in a TFLite Edge TPU model to enable acceleration.
