from app.hal.buttons import ButtonEvent, Buttons
from app.hal.fuel_gauge import FuelGauge


class FakeBus:
    def __init__(self, regs):
        self.regs = regs

    def read_i2c_block_data(self, addr, reg, n):
        assert addr == 0x36 and n == 2
        return self.regs[reg]


def gauge(regs, **cfg):
    return FuelGauge({"enabled": True, **cfg}, bus=FakeBus(regs))


def test_percent_voltage_rate():
    g = gauge({0x04: [57, 128], 0x02: [0xD0, 0x00], 0x16: [0xFF, 0xF6]})
    assert g.percent() == 57.5
    assert abs(g.voltage() - 0xD000 * 78.125e-6) < 1e-9   # ~4.16 V
    assert abs(g.charge_rate() - (-10 * 0.208)) < 1e-9    # discharging


def test_low_threshold():
    assert gauge({0x04: [9, 0]}).is_low()
    assert not gauge({0x04: [11, 0]}).is_low()
    assert gauge({0x04: [20, 0]}, low_percent=25).is_low()


def test_disabled_returns_none():
    g = FuelGauge({"enabled": False})
    assert not g.available()
    assert g.percent() is None and not g.is_low()


def test_read_error_returns_none():
    class Broken:
        def read_i2c_block_data(self, *a):
            raise OSError("nack")

    g = FuelGauge({"enabled": True}, bus=Broken())
    assert g.percent() is None


def test_hold_language_gives_battery():
    b = Buttons({"enabled": False})

    class FakeBtn:
        when_pressed = when_held = when_released = None

    btn = FakeBtn()
    b._attach(btn, ButtonEvent.LANG_TOGGLE)
    btn.when_released()
    btn.when_held(); btn.when_released()
    assert b.poll() == [ButtonEvent.LANG_TOGGLE, ButtonEvent.BATTERY]
