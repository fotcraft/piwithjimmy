"""Battery fuel gauge (MAX17048) on the Readable IO board, read over I2C.

Gives the battery charge in percent so the device can say it out loud, and
lets the orchestrator warn before the cell runs flat. See docs/IO_BOARD.md.

Needs I2C on the Pi (`dtparam=i2c_arm=on` in /boot/firmware/config.txt) and
the smbus2 package. Without either, or with hardware.fuel_gauge.enabled false,
every reading returns None and the device behaves as before.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REG_VCELL = 0x02    # 78.125 uV per LSB
REG_SOC = 0x04      # high byte = %, low byte = 1/256 %
REG_VERSION = 0x08
REG_CRATE = 0x16    # signed, 0.208 %/hour per LSB

VCELL_LSB = 78.125e-6
CRATE_LSB = 0.208


class FuelGauge:
    def __init__(self, config: Optional[Dict[str, Any]] = None, bus: Any = None) -> None:
        cfg = config or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.address = int(cfg.get("address", 0x36))
        self.low_percent = float(cfg.get("low_percent", 10))
        self._bus = bus
        if not self.enabled or self._bus is not None:
            return
        try:
            from smbus2 import SMBus  # type: ignore

            self._bus = SMBus(int(cfg.get("i2c_bus", 1)))
        except Exception as exc:
            logger.warning("Fuel gauge: I2C unavailable (%s)", exc)
            self._bus = None

    def available(self) -> bool:
        return self.enabled and self._bus is not None

    def _read(self, reg: int) -> Optional[List[int]]:
        if not self.available():
            return None
        try:
            return list(self._bus.read_i2c_block_data(self.address, reg, 2))
        except Exception as exc:
            logger.warning("Fuel gauge: read 0x%02X failed (%s)", reg, exc)
            return None

    def percent(self) -> Optional[float]:
        data = self._read(REG_SOC)
        if data is None:
            return None
        return max(0.0, min(100.0, data[0] + data[1] / 256.0))

    def voltage(self) -> Optional[float]:
        data = self._read(REG_VCELL)
        if data is None:
            return None
        return ((data[0] << 8) | data[1]) * VCELL_LSB

    def charge_rate(self) -> Optional[float]:
        """Percent per hour; positive while charging."""
        data = self._read(REG_CRATE)
        if data is None:
            return None
        raw = (data[0] << 8) | data[1]
        if raw & 0x8000:
            raw -= 0x10000
        return raw * CRATE_LSB

    def is_low(self) -> bool:
        pct = self.percent()
        return pct is not None and pct <= self.low_percent

    def close(self) -> None:
        if self._bus is not None and hasattr(self._bus, "close"):
            try:
                self._bus.close()
            except Exception:
                pass
