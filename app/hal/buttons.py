from enum import Enum
from typing import List


class ButtonEvent(str, Enum):
    SCAN = "scan"
    REPEAT = "repeat"
    VOL_UP = "vol_up"
    VOL_DOWN = "vol_down"
    LANG_TOGGLE = "lang_toggle"


class Buttons:
    """
    GPIO stub. Replace with actual GPIO handling.
    For dev/testing, you can call simulate() to inject events.
    """

    def __init__(self) -> None:
        self._queue: List[ButtonEvent] = []

    def poll(self) -> List[ButtonEvent]:
        events = list(self._queue)
        self._queue.clear()
        return events

    def simulate(self, event: ButtonEvent) -> None:
        self._queue.append(event)
