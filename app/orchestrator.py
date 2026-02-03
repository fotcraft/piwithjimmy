import time
from typing import Any, Dict

from app.hal.audio import AudioOutput
from app.hal.buttons import Buttons, ButtonEvent
from app.hal.camera import Camera
from app.hal.leds import Leds
from app.language.detect import detect_language
from app.language.normalize import normalize_text
from app.storage.last_result import LastResultStore
from app.vision.pipeline import VisionPipeline, VisionResult


class Orchestrator:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.device_cfg = config.get("device", {})
        self.quality_cfg = config.get("quality", {})
        self.ocr_cfg = config.get("ocr", {})

        self.buttons = Buttons()
        self.leds = Leds()
        self.camera = Camera(config.get("camera", {}))
        self.audio = AudioOutput(config)
        self.vision = VisionPipeline(config)
        self.storage = LastResultStore(config.get("storage", {}))

        self.language_override = self.device_cfg.get("language_mode", "auto")

    def run(self) -> None:
        while True:
            events = self.buttons.poll()
            for event in events:
                self._handle_button(event)
            time.sleep(0.05)

    def _handle_button(self, event: ButtonEvent) -> None:
        if event == ButtonEvent.SCAN:
            self.handle_scan()
        elif event == ButtonEvent.REPEAT:
            self.handle_repeat()
        elif event == ButtonEvent.VOL_UP:
            self.audio.adjust_volume(delta=5)
        elif event == ButtonEvent.VOL_DOWN:
            self.audio.adjust_volume(delta=-5)
        elif event == ButtonEvent.LANG_TOGGLE:
            self._toggle_language()

    def _toggle_language(self) -> None:
        if self.language_override == "el":
            self.language_override = "en"
        elif self.language_override == "en":
            self.language_override = "auto"
        else:
            self.language_override = "el"

    def handle_scan(self) -> None:
        self.audio.play_prompt("capturing", self._current_lang_hint())
        image = self._capture_image()
        if image is None:
            self.audio.play_prompt("camera_error", self._current_lang_hint())
            return

        result = self._run_vision(image)
        if not result:
            return
        self._speak_result(result)

    def handle_scan_with_image(self, image) -> None:
        result = self._run_vision(image, skip_quality=True)
        if not result:
            return

        self._speak_result(result)

    def _speak_result(self, result: VisionResult) -> None:
        lang = self._resolve_language(result.text)
        cleaned = normalize_text(result.text)
        if result.confidence < float(self.ocr_cfg.get("min_confidence", 0)):
            self.audio.play_prompt("not_sure", lang)
            return

        self.storage.save(cleaned, lang)
        self.audio.play_prompt("reading", lang)
        self.audio.speak_text(cleaned, lang)

    def handle_repeat(self) -> None:
        last = self.storage.load()
        if not last:
            self.audio.play_prompt("no_text", self._current_lang_hint())
            return
        self.audio.speak_text(last["text"], last["lang"])

    def _capture_image(self):
        try:
            self.leds.on()
            image = self.camera.capture()
            return image
        finally:
            self.leds.off()

    def _run_vision(self, image, skip_quality: bool = False) -> VisionResult | None:
        result = self.vision.process(image, skip_quality=skip_quality)
        if result.status == "bad_quality":
            if result.reason == "blur":
                self.audio.play_prompt("too_blurry", self._current_lang_hint())
            elif result.reason == "dark":
                self.audio.play_prompt("too_dark", self._current_lang_hint())
            else:
                self.audio.play_prompt("not_sure", self._current_lang_hint())
            return None
        if result.status == "no_text":
            self.audio.play_prompt("no_text", self._current_lang_hint())
            return None
        if result.status == "error":
            self.audio.play_prompt("not_sure", self._current_lang_hint())
            return None
        return result

    def _resolve_language(self, text: str) -> str:
        override = self.language_override
        if override in ("el", "en"):
            return override
        return detect_language(text)

    def _current_lang_hint(self) -> str:
        if self.language_override in ("el", "en"):
            return self.language_override
        return "en"

    def wait_for_audio(self) -> None:
        self.audio.wait_idle()
