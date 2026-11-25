from tools.benchmark import cer, normalise


def test_cer_identical():
    assert cer("Καλημέρα κόσμε", "καλημέρα   κόσμε") == 0.0


def test_cer_one_error():
    assert abs(cer("abcd", "abce") - 0.25) < 1e-9


def test_accents_matter():
    assert cer("καλημέρα", "καλημερα") > 0


def test_normalise_nfc():
    assert normalise("Έ") == normalise("Έ".lower())
