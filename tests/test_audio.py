from app.hal.audio import _decode_fmt, _encode_fmt, build_ssml


def test_ssml_escapes_ocr_text():
    ssml = build_ssml("Tom & Jerry <3", "el-GR-AthinaNeural", "el-GR")
    assert "Tom &amp; Jerry &lt;3" in ssml
    assert "<voice name='el-GR-AthinaNeural'>" in ssml


def test_ssml_rate():
    ssml = build_ssml("hi", "v", "en-US", "-5%")
    assert "<prosody rate='-5%'>hi</prosody>" in ssml


def test_prompt_format_roundtrip():
    payload = "volume" + _encode_fmt({"n": 60})
    assert _decode_fmt(payload) == ("volume", {"n": "60"})
    assert _decode_fmt("ready") == ("ready", {})
