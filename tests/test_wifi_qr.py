import subprocess

import cv2
import numpy as np
import pytest

from app import wifi_qr
from app.hal.buttons import ButtonEvent
from app.orchestrator import Orchestrator, _speakable_ssid
from app.wifi_qr import WifiCredentials, find_wifi_qr, join, nmcli_command, parse_wifi_qr


# ------------------------------------------------------------------ parsing
def test_parse_basic():
    c = parse_wifi_qr("WIFI:T:WPA;S:Papadopoulos_Home;P:s3cret pass;;")
    assert (c.ssid, c.password, c.security, c.hidden) == ("Papadopoulos_Home", "s3cret pass", "WPA", False)


def test_parse_escapes_and_field_order():
    c = parse_wifi_qr(r'WIFI:P:a\;b\:c\\d\,e;H:true;S:My\;Net;T:WPA;;')
    assert c.ssid == "My;Net"
    assert c.password == "a;b:c\\d,e"
    assert c.hidden


def test_parse_open_network_and_greek_ssid():
    c = parse_wifi_qr("WIFI:S:Καφέ Ελλάς;T:nopass;;")
    assert c.ssid == "Καφέ Ελλάς" and c.security == "nopass" and c.password == ""
    assert c.supported


def test_parse_missing_type_defaults():
    assert parse_wifi_qr("WIFI:S:x;P:y;;").security == "WPA"
    assert parse_wifi_qr("WIFI:S:x;;").security == "nopass"


def test_parse_rejects_other_codes():
    assert parse_wifi_qr("https://example.com") is None
    assert parse_wifi_qr("WIFI:T:WPA;P:nossid;;") is None
    assert parse_wifi_qr("") is None


def test_wep_unsupported_and_password_not_in_repr():
    c = parse_wifi_qr("WIFI:T:WEP;S:old;P:topsecret;;")
    assert not c.supported
    assert "topsecret" not in repr(c)


# ---------------------------------------------------------------- detection
def _qr_image(payload: str, size: int = 2304) -> np.ndarray:
    qr = cv2.QRCodeEncoder.create().encode(payload)
    qr = cv2.resize(qr, (400, 400), interpolation=cv2.INTER_NEAREST)
    canvas = np.full((1296, size), 255, np.uint8)
    canvas[400:800, 900:1300] = qr
    return cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)


def test_find_in_camera_sized_photo():
    c = find_wifi_qr(_qr_image("WIFI:T:WPA;S:Readable Test;P:pw12345678;;"))
    assert c is not None and c.ssid == "Readable Test"


def test_non_wifi_qr_and_blank_page_ignored():
    assert find_wifi_qr(_qr_image("https://example.com")) is None
    assert find_wifi_qr(np.full((1296, 2304, 3), 255, np.uint8)) is None


# --------------------------------------------------------------------- join
def test_nmcli_command():
    cmd = nmcli_command(WifiCredentials("Home Net", "pw", "WPA", hidden=True))
    assert cmd == ["nmcli", "--wait", "40", "device", "wifi", "connect", "Home Net",
                   "password", "pw", "hidden", "yes"]
    assert "password" not in nmcli_command(WifiCredentials("Open", "", "nopass"))


def test_join_success_and_failure():
    calls = []

    def ok(cmd, timeout):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def fail(cmd, timeout):
        return subprocess.CompletedProcess(cmd, 4, "", "Error: Secrets were required")

    creds = WifiCredentials("Home", "pw")
    assert join(creds, runner=ok) and calls[0][:6] == ["nmcli", "--wait", "40", "device", "wifi", "connect"]
    assert not join(creds, runner=fail)
    assert not join(WifiCredentials("Old", "pw", "WEP"), runner=ok)


def test_join_missing_nmcli():
    def missing(cmd, timeout):
        raise FileNotFoundError

    assert not join(WifiCredentials("Home", "pw"), runner=missing)


# ------------------------------------------------------------- orchestrator
class FakeAudio:
    def __init__(self):
        self.said = []

    def play_prompt(self, key, lang, **kw):
        self.said.append(key)

    def speak_text(self, text, lang):
        self.said.append(("text", text))

    def stop(self):
        pass


class FakeButtons:
    def __init__(self, events):
        self.events = list(events)

    def wait(self, timeout=0.1):
        return self.events.pop(0) if self.events else None


def _orch(events, monkeypatch, join_ok=True):
    o = Orchestrator.__new__(Orchestrator)
    o.audio, o.buttons = FakeAudio(), FakeButtons(events)
    o.wifi_cfg = {"confirm_timeout_seconds": 0.5}
    o.language_override, o.prompt_language = "auto", "el"
    joined = []
    monkeypatch.setattr(wifi_qr, "join", lambda creds, timeout: joined.append(creds) or join_ok)
    return o, joined


def test_confirm_with_scan_joins(monkeypatch):
    o, joined = _orch([ButtonEvent.LOW_BATTERY, ButtonEvent.SCAN], monkeypatch)
    assert o.handle_wifi_qr(WifiCredentials("Home_Net-5G", "pw"))
    assert joined and o.audio.said == ["wifi_found", ("text", "Home Net 5G"), "wifi_confirm",
                                       "wifi_connecting", "wifi_connected"]


def test_other_button_or_timeout_cancels(monkeypatch):
    o, joined = _orch([ButtonEvent.VOL_UP], monkeypatch)
    assert not o.handle_wifi_qr(WifiCredentials("Home", "pw"))
    o2, joined2 = _orch([], monkeypatch)
    assert not o2.handle_wifi_qr(WifiCredentials("Home", "pw"))
    assert not joined and not joined2
    assert o.audio.said[-1] == "wifi_cancelled" == o2.audio.said[-1]


def test_failed_join_is_announced(monkeypatch):
    o, _ = _orch([ButtonEvent.SCAN], monkeypatch, join_ok=False)
    assert not o.handle_wifi_qr(WifiCredentials("Home", "pw"))
    assert o.audio.said[-1] == "wifi_failed"


def test_speakable_ssid():
    assert _speakable_ssid("COSMOTE-1a2b_5G") == "COSMOTE 1a2b 5G"
    assert _speakable_ssid("___") == "___"
