import numpy as np
import pytest

from app import net
from app.vision.pipeline import VisionPipeline
from app.vision.types import OcrResult

IMG = np.zeros((50, 50, 3), dtype=np.uint8)


class FakeEngine:
    def __init__(self, result, configured=True, name="x"):
        self.result = result
        self.configured = configured
        self.calls = 0
        self.endpoint = f"https://{name}.example"
        self.provider = name

    def is_configured(self):
        return self.configured

    def run(self, image):
        self.calls += 1
        return self.result

    def base_url(self):
        return self.endpoint


class FakeLocal:
    backend = "tesseract"

    def __init__(self, text="local text", conf=60.0):
        self.out = (text, conf)
        self.calls = 0

    def run(self, image):
        self.calls += 1
        return self.out


class PassQuality:
    def check(self, image):
        return True, "ok"


@pytest.fixture(autouse=True)
def online(monkeypatch):
    monkeypatch.setattr(net, "is_reachable", lambda url, **k: True)


def make(cloud, vlm, local=None, **cfg):
    config = {"cloud_ocr": {"primary": True}, "vlm": cfg}
    return VisionPipeline(config, cloud=cloud, vlm=vlm, local=local or FakeLocal(), quality=PassQuality())


def test_printed_text_uses_azure_only():
    cloud = FakeEngine(OcrResult("Bill 42 EUR", 95.0, False, "azure_read"), name="az")
    vlm = FakeEngine(OcrResult("vlm", 80.0, True, "vlm_x"), name="vlm")
    res = make(cloud, vlm).process(IMG)
    assert res.source == "azure_read" and vlm.calls == 0


def test_handwriting_goes_to_vlm():
    cloud = FakeEngine(OcrResult("Ayamnth Mapia", 75.0, True, "azure_read"), name="az")
    vlm = FakeEngine(OcrResult("Αγαπητή Μαρία", 80.0, True, "vlm_x"), name="vlm")
    res = make(cloud, vlm).process(IMG)
    assert res.text == "Αγαπητή Μαρία" and res.source == "vlm_x"


def test_english_lock_keeps_azure_for_handwriting():
    cloud = FakeEngine(OcrResult("Dear Maria", 85.0, True, "azure_read"), name="az")
    vlm = FakeEngine(OcrResult("x", 80.0, True, "vlm_x"), name="vlm")
    res = make(cloud, vlm).process(IMG, lang_hint="en")
    assert res.source == "azure_read" and vlm.calls == 0


def test_low_confidence_goes_to_vlm():
    cloud = FakeEngine(OcrResult("???", 30.0, False, "azure_read"), name="az")
    vlm = FakeEngine(OcrResult("clear text", 80.0, True, "vlm_x"), name="vlm")
    assert make(cloud, vlm).process(IMG).source == "vlm_x"


def test_vlm_failure_falls_back_to_azure_text():
    cloud = FakeEngine(OcrResult("Ayamnth", 75.0, True, "azure_read"), name="az")
    vlm = FakeEngine(None, name="vlm")
    assert make(cloud, vlm).process(IMG).source == "azure_read"


def test_offline_uses_local(monkeypatch):
    monkeypatch.setattr(net, "is_reachable", lambda url, **k: False)
    cloud = FakeEngine(OcrResult("never", 99.0), name="az")
    vlm = FakeEngine(OcrResult("never", 99.0), name="vlm")
    local = FakeLocal("Τοπικό κείμενο", 70.0)
    res = make(cloud, vlm, local).process(IMG)
    assert res.text == "Τοπικό κείμενο" and res.source == "local_tesseract"
    assert cloud.calls == 0 and vlm.calls == 0


def test_nothing_found():
    cloud = FakeEngine(OcrResult("", 0.0), name="az")
    vlm = FakeEngine(OcrResult("", 0.0), name="vlm")
    res = make(cloud, vlm, FakeLocal("", 0.0)).process(IMG)
    assert res.status == "no_text"


def test_engine_exception_returns_error():
    class Boom(FakeEngine):
        def run(self, image):
            raise RuntimeError("boom")

    res = make(Boom(None, name="az"), FakeEngine(None, configured=False)).process(IMG)
    assert res.status == "error"


def test_bad_quality_short_circuits():
    class Dark:
        def check(self, image):
            return False, "dark"

    p = VisionPipeline({}, cloud=FakeEngine(None), vlm=FakeEngine(None), local=FakeLocal(), quality=Dark())
    assert p.process(IMG).reason == "dark"
