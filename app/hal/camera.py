"""Camera Module 3 capture via picamera2.

- Runs an autofocus cycle before every capture (Camera Module 3 has
  autofocus; without this, pages at different distances come out blurry).
- Uses RGB888, which picamera2 delivers in BGR byte order, i.e. what
  OpenCV expects.
- Default resolution 2304x1296 (the sensor's fast binned mode): enough detail
  for a full A4 page at ~25 cm.
"""
import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)


class Camera:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.width = int(config.get("width", 2304))
        self.height = int(config.get("height", 1296))
        self.warmup_ms = int(config.get("warmup_ms", 300))
        self.autofocus = bool(config.get("autofocus", True))
        self._picam2 = None
        self._has_af = False

    def _ensure_camera(self) -> None:
        if self._picam2 is not None:
            return
        try:
            from picamera2 import Picamera2  # type: ignore
        except Exception as exc:  # pragma: no cover - hardware import
            raise RuntimeError("picamera2 not available") from exc

        self._picam2 = Picamera2()
        cfg = self._picam2.create_still_configuration(
            main={"size": (self.width, self.height), "format": "RGB888"}
        )
        self._picam2.configure(cfg)
        self._picam2.start()
        self._has_af = "AfMode" in self._picam2.camera_controls
        if self.autofocus and self._has_af:
            from libcamera import controls  # type: ignore

            self._picam2.set_controls({"AfMode": controls.AfModeEnum.Auto})
        time.sleep(self.warmup_ms / 1000.0)

    def capture(self):
        self._ensure_camera()
        if self.autofocus and self._has_af:
            try:
                if not self._picam2.autofocus_cycle():
                    logger.info("Autofocus did not lock; capturing anyway")
            except Exception as exc:
                logger.warning("Autofocus failed: %s", exc)
        return self._picam2.capture_array("main")

    def close(self) -> None:
        if self._picam2 is not None:
            self._picam2.close()
            self._picam2 = None
