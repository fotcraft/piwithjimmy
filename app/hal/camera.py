import time
from typing import Any, Dict


class Camera:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.width = int(config.get("width", 1280))
        self.height = int(config.get("height", 720))
        self.warmup_ms = int(config.get("warmup_ms", 300))
        self._picam2 = None

    def _ensure_camera(self) -> None:
        if self._picam2 is not None:
            return
        try:
            from picamera2 import Picamera2
        except Exception as exc:  # pragma: no cover - hardware import
            raise RuntimeError("picamera2 not available") from exc

        self._picam2 = Picamera2()
        config = self._picam2.create_still_configuration(
            main={"size": (self.width, self.height)}
        )
        self._picam2.configure(config)
        self._picam2.start()

    def capture(self):
        self._ensure_camera()
        time.sleep(self.warmup_ms / 1000.0)
        return self._picam2.capture_array()
