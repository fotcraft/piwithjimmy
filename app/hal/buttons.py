"""Physical buttons and the PowerBoost low-battery signal, via gpiozero.

Layout: one large Scan button on the front, four small side buttons
(Repeat, Volume +, Volume -, Language). Holding Repeat speaks the help text.

All buttons wire between a GPIO pin and GND; the internal pull-ups are used.
Pin numbers are BCM and are set in config.yaml (hardware.buttons).
See docs/WIRING.md.

Without gpiozero (e.g. on a laptop) the class falls back to a stub, and events
can be injected with simulate() or the --keys option of main.py.
"""
import logging
import queue
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ButtonEvent(str, Enum):
    SCAN = "scan"
    REPEAT = "repeat"
    VOL_UP = "vol_up"
    VOL_DOWN = "vol_down"
    LANG_TOGGLE = "lang_toggle"
    HELP = "help"
    LOW_BATTERY = "low_battery"


# Which button produces which event when held instead of pressed.
HOLD_EVENTS = {ButtonEvent.REPEAT: ButtonEvent.HELP}


class Buttons:
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self._queue: "queue.Queue[ButtonEvent]" = queue.Queue()
        self._devices: List[Any] = []
        self.hardware = False
        self.hold_seconds = float(cfg.get("hold_seconds", 1.5))
        pins: Dict[str, int] = cfg.get("pins", {}) or {}
        low_batt_pin = cfg.get("low_battery_pin")
        if not cfg.get("enabled", True) or not pins:
            logger.info("Buttons: GPIO disabled, using simulated input")
            return
        try:
            from gpiozero import Button, DigitalInputDevice  # type: ignore
        except Exception as exc:  # not on a Pi
            logger.warning("Buttons: gpiozero unavailable (%s), using simulated input", exc)
            return

        try:
            for name, pin in pins.items():
                event = ButtonEvent(name)
                btn = Button(int(pin), pull_up=True, bounce_time=0.03, hold_time=self.hold_seconds)
                self._attach(btn, event)
                self._devices.append(btn)
            if low_batt_pin is not None:
                lbo = DigitalInputDevice(int(low_batt_pin), pull_up=True, bounce_time=1.0)
                # PowerBoost LBO goes LOW when the cell drops below ~3.2 V.
                lbo.when_deactivated = lambda: self._queue.put(ButtonEvent.LOW_BATTERY)
                self._devices.append(lbo)
            self.hardware = True
            logger.info("Buttons: GPIO ready (%s)", ", ".join(f"{k}={v}" for k, v in pins.items()))
        except Exception as exc:
            logger.error("Buttons: GPIO setup failed (%s), using simulated input", exc)
            self.close()

    def _attach(self, btn: Any, event: ButtonEvent) -> None:
        hold_event = HOLD_EVENTS.get(event)
        if hold_event is None:
            btn.when_pressed = lambda: self._queue.put(event)
            return
        # Press-and-release -> event; hold -> hold_event (fires once).
        state = {"held": False}

        def on_held() -> None:
            state["held"] = True
            self._queue.put(hold_event)

        def on_released() -> None:
            if not state["held"]:
                self._queue.put(event)
            state["held"] = False

        btn.when_held = on_held
        btn.when_released = on_released

    def poll(self) -> List[ButtonEvent]:
        events = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                return events

    def wait(self, timeout: float = 0.1) -> Optional[ButtonEvent]:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def simulate(self, event: ButtonEvent) -> None:
        self._queue.put(event)

    def close(self) -> None:
        for dev in self._devices:
            try:
                dev.close()
            except Exception:
                pass
        self._devices.clear()
