"""Arabic text normalization for symptom matching.

Egyptian users type the same idea many ways: with/without hamza, ة vs ه, ي vs ى,
extra spaces, English/Arabic digits mixed. We collapse all that to one canonical
form so fuzzy matching against the dataset symptoms isn't fighting orthography.
"""

from __future__ import annotations

import re
import unicodedata

# Arabic diacritics (tashkeel) — strip them, users rarely type them
_DIACRITICS = re.compile(r"[\u064B-\u0652\u0670\u0640]")

# Characters that get unified to a canonical form
_REPLACEMENTS = {
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي",
    "ؤ": "و",
    "ة": "ه",
    "ـ": "",   # tatweel
}

# Eastern Arabic digits → Western
_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize(text: str) -> str:
    """Return a canonical, lowercased, diacritic-free version of `text`."""
    if not text:
        return ""
    # Unicode NFKC folds compatibility variants (e.g. full-width to half-width)
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_DIGIT_MAP)
    text = _DIACRITICS.sub("", text)
    for src, dst in _REPLACEMENTS.items():
        text = text.replace(src, dst)
    text = text.lower()
    # Collapse repeated whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokens(text: str) -> list[str]:
    """Tokenize on whitespace and punctuation after normalization."""
    norm = normalize(text)
    return [t for t in re.split(r"[\s,،.!؟?؛;:\-/]+", norm) if t]
