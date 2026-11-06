Readable - Portable Text Reader (piwithjimmy)

A handheld reader for blind and visually impaired people, built on a
Raspberry Pi Compute Module 5. Press the big button: it photographs the page
and reads it aloud in Greek or English.

How it reads
1. Camera Module 3 photo, with autofocus and an illumination LED.
2. Quality check: tells the user out loud if the photo is blurry, too dark or too bright.
3. Azure OCR (Read API, or Document Intelligence with provider: azure_docintel).
4. Handwriting (Greek in particular), low confidence or no text: a vision-language
   model (Azure OpenAI, OpenAI or Anthropic; see vlm in config.yaml).
5. Offline: local Tesseract (Greek + English print) and espeak-ng voice.
6. Azure Neural TTS (el-GR-AthinaNeural / en-US-JennyNeural). Spoken prompts
   are cached on disk, so they keep the natural voice offline.

Controls
- Big front button: scan and read
- Repeat: read the last text again (hold for spoken help)
- Volume + / -: spoken volume level
- Language: Greek -> English -> automatic (announced out loud)
- Any button while reading stops the speech
- Says "Battery low" when the PowerBoost LBO signal drops

Hardware
- Raspberry Pi Compute Module 5 (2GB RAM, 16GB eMMC, Wi-Fi)
- Waveshare CM5-NANO-B carrier board
- Raspberry Pi Camera Module 3 (autofocus)
- MAX98357A I2S amplifier + 3W 4ohm 40mm speaker
- Adafruit PowerBoost 1000C + 3.7V LiPo
- 1 large + 4 small tactile buttons, status LED, white illumination LED
- 3D-printed enclosure: design_enclosure/
Wiring and pin map: docs/WIRING.md

Install (on the device)

1) System packages:
   sudo apt update
   sudo apt install -y python3-picamera2 python3-gpiozero python3-lgpio \
       python3-opencv tesseract-ocr tesseract-ocr-ell espeak-ng pulseaudio-utils

2) Python environment:
   python3 -m venv --system-site-packages .venv
   source .venv/bin/activate
   pip install -r requirements.txt

3) Keys (never commit them):
   cp deploy/readable.env.example ~/.config/readable/readable.env  (then edit)
   Azure resources: Computer Vision (OCR), Speech (TTS), and for handwriting an
   Azure OpenAI vision deployment (or an OpenAI / Anthropic key).

4) Run:
   python3 main.py                  # normal operation (GPIO buttons)
   python3 main.py --keys           # simulate buttons from the keyboard
   python3 main.py --image page.jpg # pipeline on a photo, no camera
   python3 main.py --warm-cache     # pre-synthesise prompts for offline use

5) Start at boot: see deploy/readable.service

Testing
   pip install -r requirements-dev.txt
   python3 -m pytest                # unit tests, no hardware or keys needed

Measuring accuracy
   python3 tools/benchmark.py bench/   # photos + ground-truth .txt per category
   Reports accuracy (1 - character error rate), time per scan and which engine
   answered. See the docstring in tools/benchmark.py for the folder layout.

Project structure
   main.py                 Entry point
   config.yaml             All settings
   app/orchestrator.py     Buttons -> scan -> speak flow
   app/net.py              Fast offline detection
   app/vision/pipeline.py  Engine routing (Azure -> VLM -> local)
   app/vision/cloud_ocr.py Azure Read / Document Intelligence
   app/vision/vlm_ocr.py   Vision-language model OCR (handwriting)
   app/vision/ocr.py       Local OCR (Tesseract)
   app/hal/                Camera, audio, buttons, LEDs
   app/prompts/phrases.py  Spoken prompts (Greek, English)
   tools/                  Benchmark and debug scripts
   tests/                  Unit tests
   deploy/                 systemd service, env template
   docs/WIRING.md          Pin map and wiring
   design_enclosure/       Enclosure CAD (parametric) and component models

Notes
- Azure handwriting OCR covers 9 languages, not Greek; the VLM handles Greek handwriting.
- Microsoft lists Greek print for Document Intelligence Read but not for the
  Vision Read API. If Greek print is weak, set cloud_ocr.provider: azure_docintel.
