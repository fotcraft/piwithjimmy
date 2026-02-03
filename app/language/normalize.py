import re


_MULTI_SPACE = re.compile(r"\s+")
_REPEAT_PUNCT = re.compile(r"([!?.])\1{2,}")


def normalize_text(text: str) -> str:
    cleaned = text.replace("\n", " ").replace("\r", " ")
    cleaned = _MULTI_SPACE.sub(" ", cleaned).strip()
    cleaned = _REPEAT_PUNCT.sub(r"\1\1", cleaned)
    return cleaned
