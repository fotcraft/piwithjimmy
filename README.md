piwithjimmy - Portable Text Reader

A portable text reader powered by Raspberry Pi and Azure AI.
Captures handwritten or printed notes with a camera, reads them aloud
using Azure Computer Vision (OCR) and Azure Neural Text-to-Speech.

Features
- Azure Read API as primary OCR (handwriting + printed text)
- Azure Neural TTS (en-US-JennyNeural / el-GR-AthinaNeural)
- Auto language detection (English + Greek)
- Local OCR fallback (EasyOCR/Tesseract) when Azure is unavailable
- espeak-ng TTS fallback when Azure Speech is unavailable
- Scan/Repeat/Volume/Language buttons via GPIO
- Camera capture via picamera2
- Image quality checks (blur/exposure)
- Last-result storage for Repeat

Hardware (target build)
- Raspberry Pi Compute Module 5 (2GB RAM, 16GB eMMC, WiFi)
- Waveshare CM5-NANO-B carrier board
- Raspberry Pi Camera Module 3 (autofocus)
- MAX98357A I2S amplifier + 3W 4ohm speaker
- Adafruit PowerBoost 1000C + 3.7V 3000mAh LiPo battery
- 5x tactile push buttons + status LED

Quick start

1) Install system dependencies:
   sudo apt-get update
   sudo apt-get install -y python3-picamera2 python3-opencv tesseract-ocr espeak-ng

2) Python deps:
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt

3) Set Azure credentials:
   export AZURE_CV_KEY="your-computer-vision-key"
   export AZURE_SPEECH_KEY="your-speech-service-key"

   Azure resources needed:
   - Computer Vision (for OCR) - endpoint configured in config.yaml
   - Speech Service (for TTS) - region configured in config.yaml

4) Run:
   python3 main.py --config config.yaml

Testing without a camera
   python3 main.py --image /path/to/test.jpg

Configuration (config.yaml)
- device.language_mode: auto|en|el (default: auto)
- cloud_ocr.enabled: true/false (Azure Read API)
- cloud_ocr.primary: true/false (Azure-first vs local-first)
- tts.azure_enabled: true/false (Azure Neural TTS)
- tts.azure_region: Azure Speech Service region (e.g. italynorth)
- ocr.preprocess: false recommended for handwriting

Project structure
   config.yaml          - All configuration
   main.py              - Entry point (--image, --once, --config)
   app/
     orchestrator.py    - Main scan/repeat/speak flow
     vision/
       pipeline.py      - Azure-first or local-first OCR pipeline
       cloud_ocr.py     - Azure Read API client
       ocr.py           - Local OCR (EasyOCR/Tesseract/PaddleOCR)
       quality.py       - Blur/exposure checks
       text_detector.py - Text region detection (stub for TPU)
     hal/
       audio.py         - Azure Neural TTS + espeak-ng fallback
       buttons.py       - GPIO button input (stub)
       camera.py        - picamera2 capture
       leds.py          - Status LED (stub)
     language/
       detect.py        - Greek/English detection
       normalize.py     - Text normalization
     prompts/
       phrases.py       - UI prompt phrases
     storage/
       last_result.py   - Last-result persistence
   design_enclosure/    - STEP/CAD files for enclosure design

Notes
- GPIO wiring is stubbed. Replace app/hal/buttons.py and
  app/hal/leds.py with your actual GPIO logic.
- Azure handwriting recognition works best for English.
  Greek works well for printed text.
- Audio uses paplay (PipeWire/PulseAudio) for WAV playback.
