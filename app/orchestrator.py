import logging
import time
from typing import Any, Dict, Optional

from app.hal.audio import AudioOutput
from app.hal.buttons import ButtonEvent, Buttons
from app.hal.camera import Camera
from app.hal.fuel_gauge import FuelGauge
from app.hal.leds import Leds
from app.language.detect import detect_language
from app.language.normalize import normalize_text
from app.storage.last_result import LastResultStore
from app.vision.pipeline import VisionPipeline, VisionResult

logger = logging.getLogger(__name__)

LANG_CYCLE = {"el": "en", "en": "auto", "auto": "el"}
QUALITY_PROMPTS = {"blur": "too_blurry", "dark": "too_dark", "bright": "too_bright"}
LOW_BATTERY_REPEAT_S = 600
BATTERY_POLL_S = 60


class Orchestrator:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.device_cfg = config.get("device", {})
        self.ocr_cfg = config.get("ocr", {})
        hw = config.get("hardware", {})

        self.buttons = Buttons(hw.get("buttons", {}))
        self.leds = Leds(hw)
        self.camera = Camera(config.get("camera", {}))
        self.audio = AudioOutput(config)
        self.vision = VisionPipeline(config)
        self.storage = LastResultStore(config.get("storage", {}))
        self.gauge = FuelGauge(hw.get("fuel_gauge", {}))

        self.language_override = self.device_cfg.get("language_mode", "auto")
        self.prompt_language = self.device_cfg.get("prompt_language", "el")
        self._last_lang: Optional[str] = None
        self._last_low_battery = 0.0
        self._last_battery_poll = 0.0

    # ----------------------------------------------------------------- loop
    def run(self) -> None:
        self.audio.play_prompt("ready", self._prompt_lang())
        while True:
            event = self.buttons.wait(timeout=0.1)
            if event is not None:
                self.handle_event(event)
            else:
                self._poll_battery()

    def handle_event(self, event: ButtonEvent) -> None:
        logger.info("Button: %s", event.value)
        if event == ButtonEvent.LOW_BATTERY:
            self._announce_low_battery()
            return
        # Any button press interrupts speech in progress.
        was_speaking = self.audio.is_busy()
        self.audio.stop()

        if event == ButtonEvent.SCAN:
            self.handle_scan()
        elif event == ButtonEvent.REPEAT:
            if not was_speaking:  # Repeat while reading = stop only
                self.handle_repeat()
        elif event == ButtonEvent.VOL_UP:
            self._volume(+10)
        elif event == ButtonEvent.VOL_DOWN:
            self._volume(-10)
        elif event == ButtonEvent.LANG_TOGGLE:
            self._toggle_language()
        elif event == ButtonEvent.HELP:
            self.audio.play_prompt("help", self._prompt_lang())
        elif event == ButtonEvent.BATTERY:
            self._announce_battery()

    # ------------------------------------------------------------- actions
    def handle_scan(self) -> None:
        self.leds.busy(True)
        try:
            self.audio.play_prompt("capturing", self._prompt_lang())
            image = self._capture_image()
            if image is None:
                self.audio.play_prompt("camera_error", self._prompt_lang())
                return
            result = self._run_vision(image)
            if result:
                self._speak_result(result)
        finally:
            self.leds.busy(False)

    def handle_scan_with_image(self, image) -> Optional[VisionResult]:
        result = self._run_vision(image, skip_quality=True)
        if result:
            self._speak_result(result)
        return result

    def handle_repeat(self) -> None:
        last = self.storage.load()
        if not last:
            self.audio.play_prompt("no_text", self._prompt_lang())
            return
        self.audio.speak_text(last["text"], last["lang"])

    def _volume(self, delta: int) -> None:
        level = self.audio.adjust_volume(delta)
        self.audio.play_prompt("volume", self._prompt_lang(), n=level)

    def _toggle_language(self) -> None:
        self.language_override = LANG_CYCLE.get(self.language_override, "auto")
        if self.language_override in ("el", "en"):
            self.prompt_language = self.language_override
        self.audio.play_prompt(f"lang_{self.language_override}", self._prompt_lang())

    def _announce_battery(self) -> None:
        pct = self.gauge.percent()
        if pct is None:
            self.audio.play_prompt("battery_unknown", self._prompt_lang())
            return
        rate = self.gauge.charge_rate()
        key = "battery_charging" if rate is not None and rate > 0.5 else "battery"
        self.audio.play_prompt(key, self._prompt_lang(), n=int(round(pct)))

    def _poll_battery(self) -> None:
        if not self.gauge.available():
            return
        now = time.monotonic()
        if self._last_battery_poll and now - self._last_battery_poll < BATTERY_POLL_S:
            return
        self._last_battery_poll = now
        if self.gauge.is_low() and not self.audio.is_busy():
            self._announce_low_battery()

    def _announce_low_battery(self) -> None:
        now = time.monotonic()
        if now - self._last_low_battery < LOW_BATTERY_REPEAT_S and self._last_low_battery:
            return
        self._last_low_battery = now
        self.audio.play_prompt("low_battery", self._prompt_lang())

    # ------------------------------------------------------------- helpers
    def _speak_result(self, result: VisionResult) -> None:
        lang = self._resolve_language(result.text)
        self._last_lang = lang
        cleaned = normalize_text(result.text)
        if result.confidence < float(self.ocr_cfg.get("min_confidence", 0)):
            self.audio.play_prompt("not_sure", lang)
            return
        self.storage.save(cleaned, lang)
        self.audio.play_prompt("reading", lang)
        self.audio.speak_text(cleaned, lang)

    def _capture_image(self):
        try:
            self.leds.on()
            return self.camera.capture()
        except Exception as exc:
            logger.error("Camera capture failed: %s", exc)
            return None
        finally:
            self.leds.off()

    def _run_vision(self, image, skip_quality: bool = False) -> Optional[VisionResult]:
        result = self.vision.process(
            image, skip_quality=skip_quality, lang_hint=self.language_override
        )
        logger.info(
            "Vision: status=%s source=%s conf=%.1f", result.status, result.source, result.confidence
        )
        if result.status == "bad_quality":
            self.audio.play_prompt(QUALITY_PROMPTS.get(result.reason, "not_sure"), self._prompt_lang())
            return None
        if result.status == "no_text":
            self.audio.play_prompt("no_text", self._prompt_lang())
            return None
        if result.status != "ok":
            self.audio.play_prompt("not_sure", self._prompt_lang())
            return None
        return result

    def _resolve_language(self, text: str) -> str:
        if self.language_override in ("el", "en"):
            return self.language_override
        return detect_language(text)

    def _prompt_lang(self) -> str:
        if self.language_override in ("el", "en"):
            return self.language_override
        return self.prompt_language

    def wait_for_audio(self) -> None:
        self.audio.wait_idle()

    def close(self) -> None:
        self.buttons.close()
        self.camera.close()
        self.gauge.close()
