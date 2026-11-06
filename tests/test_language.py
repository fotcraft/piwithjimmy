from app.language.detect import detect_language
from app.language.normalize import normalize_text


def test_greek_detected():
    assert detect_language("Καλημέρα σας, ο λογαριασμός ρεύματος") == "el"


def test_english_detected():
    assert detect_language("Your electricity bill is due") == "en"


def test_mixed_mostly_greek():
    assert detect_language("Συνταγή: Depon 500mg δύο φορές την ημέρα") == "el"


def test_empty_defaults_to_english():
    assert detect_language("") == "en"


def test_normalize_whitespace():
    assert normalize_text("a\n\nb   c!!!!") == "a b c!!"
