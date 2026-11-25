from app.hal.buttons import ButtonEvent, Buttons
from app.orchestrator import LANG_CYCLE


def test_stub_buttons_simulate_and_poll():
    b = Buttons({"enabled": False})
    b.simulate(ButtonEvent.SCAN)
    b.simulate(ButtonEvent.VOL_UP)
    assert b.poll() == [ButtonEvent.SCAN, ButtonEvent.VOL_UP]
    assert b.poll() == []


def test_hold_logic():
    b = Buttons({"enabled": False})

    class FakeBtn:
        when_pressed = when_held = when_released = None

    btn = FakeBtn()
    b._attach(btn, ButtonEvent.REPEAT)
    btn.when_released()                    # short press
    btn.when_held(); btn.when_released()   # hold
    assert b.poll() == [ButtonEvent.REPEAT, ButtonEvent.HELP]


def test_language_cycle_covers_all_modes():
    mode, seen = "auto", []
    for _ in range(3):
        mode = LANG_CYCLE[mode]
        seen.append(mode)
    assert seen == ["el", "en", "auto"]
