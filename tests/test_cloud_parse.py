from app.vision.cloud_ocr import parse_docintel_result, parse_read_result


def test_read_v32_handwriting_and_confidence():
    data = {"analyzeResult": {"readResults": [{"lines": [
        {"text": "Dear Maria", "appearance": {"style": {"name": "handwriting", "confidence": 0.9}},
         "words": [{"text": "Dear", "confidence": 0.9}, {"text": "Maria", "confidence": 0.7}]},
        {"text": "Thanks", "words": [{"text": "Thanks", "confidence": 0.8}]},
    ]}]}}
    res = parse_read_result(data)
    assert res.text == "Dear Maria\nThanks"
    assert res.handwriting is True
    assert abs(res.confidence - 80.0) < 1e-6
    assert res.source == "azure_read"


def test_docintel_parse():
    data = {"analyzeResult": {
        "pages": [{"lines": [{"content": "Λογαριασμός"}, {"content": "Ποσό 42,10 €"}],
                   "words": [{"content": "Λογαριασμός", "confidence": 0.99},
                             {"content": "Ποσό", "confidence": 0.95}]}],
        "styles": [{"isHandwritten": False, "confidence": 0.9}]}}
    res = parse_docintel_result(data)
    assert res.text == "Λογαριασμός\nΠοσό 42,10 €"
    assert res.handwriting is False
    assert res.confidence > 90


def test_empty_result():
    res = parse_read_result({"analyzeResult": {"readResults": []}})
    assert res.text == "" and res.confidence == 0.0
