import re


GREEK_RE = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]")


def detect_language(text: str) -> str:
    if not text:
        return "en"
    greek_count = len(GREEK_RE.findall(text))
    ratio = greek_count / max(len(text), 1)
    return "el" if ratio > 0.15 else "en"
