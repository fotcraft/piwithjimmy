"""Status LED (front, for carers and sighted helpers) and the white
illumination LED next to the camera (lights the page while capturing).

Pins are BCM, set in config.yaml (hardware.status_led_pin, hardware.illumination_pin).
Without gpiozero every call is a no-op.
"""
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class Leds:
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self._status = None
        self._illum = None
        if not cfg.get("enabled", True):
            return
        try:
            from gpiozero import LED  # type: ignore
        except Exception:
            return
        try:
            if cfg.get("status_led_pin") is not None:
                self._status = LED(int(cfg["status_led_pin"]))
                self._status.on()  # steady on = ready
            if cfg.get("illumination_pin") is not None:
                self._illum = LED(int(cfg["illumination_pin"]))
        except Exception as exc:
            logger.error("LED setup failed: %s", exc)

    # Illumination (used during capture)
    def on(self) -> None:
        if self._illum:
            self._illum.on()

    def off(self) -> None:
        if self._illum:
            self._illum.off()

    # Status LED: steady = ready, blinking = working
    def busy(self, active: bool) -> None:
        if not self._status:
            return
        if active:
            self._status.blink(on_time=0.15, off_time=0.15)
        else:
            self._status.on()
