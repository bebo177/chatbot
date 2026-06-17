"""Intent detection.

Cheap, dependency-free classifier: regex/keyword matching against the
normalized input. For a 520-entry domain bot, you do NOT need a transformer
here — substring matching on a curated lexicon catches >95% of real traffic
and stays in the millisecond range.

If you outgrow it, swap classify() for an embedding model behind the same
signature; the rest of the bot won't care.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from normalize import normalize


class Intent(str, Enum):
    GREETING = "greeting"
    FAREWELL = "farewell"
    HOW_ARE_YOU = "how_are_you"
    THANKS = "thanks"
    HELP = "help"
    LIST_SYSTEMS = "list_systems"
    AFFIRM = "affirm"        # answers like "أيوه" / "yes"
    DENY = "deny"            # answers like "لا" / "no"
    UNKNOWN_ANSWER = "unknown_answer"  # "مش عارف"
    DIAGNOSE = "diagnose"    # default — treat as symptom description


# Each list is matched as substrings against the normalized input.
# Normalization already folded أ/إ→ا, ة→ه, ى→ي, so write the lexicon that way.
_LEXICON: dict[Intent, list[str]] = {
    Intent.GREETING: [
        "هاي", "هلا", "اهلا", "السلام عليكم", "سلام عليكم",
        "صباح الخير", "صباح النور", "مساء الخير", "مساء النور",
        "hi", "hello", "hey", "yo", "salam",
    ],
    Intent.FAREWELL: [
        "باي", "مع السلامه", "في امان الله", "تصبح علي خير",
        "bye", "goodbye", "see you", "cya",
    ],
    Intent.HOW_ARE_YOU: [
        "ازيك", "اخبارك", "عامل ايه", "عاملة ايه", "ازي الحال",
        "how are you", "how r u", "hru", "whats up", "sup",
    ],
    Intent.THANKS: [
        "شكرا", "متشكر", "تسلم", "ربنا يخليك",
        "thanks", "thank you", "thx", "ty",
    ],
    Intent.HELP: [
        "ساعدني", "محتاج مساعده", "بتعمل ايه", "انت مين", "ايه ده",
        "help", "what can you do", "who are you",
    ],
    Intent.LIST_SYSTEMS: [
        "الانظمه", "انظمه", "اقسام", "بتشخص ايه", "بتفحص ايه",
        "what systems", "list systems",
    ],
    Intent.AFFIRM: ["ايوه", "اه", "نعم", "اكيد", "yes", "yeah", "yep", "yup", "sure"],
    Intent.DENY: ["لا", "لاء", "مش", "no", "nope", "nah"],
    Intent.UNKNOWN_ANSWER: ["مش عارف", "ميعرفش", "معرفش", "i dont know", "idk", "not sure"],
}


@dataclass
class IntentResult:
    intent: Intent
    matched_keyword: str | None = None


def classify(text: str, expecting_answer: bool = False) -> IntentResult:
    """Classify user input.

    `expecting_answer=True` biases toward AFFIRM/DENY/UNKNOWN_ANSWER, because
    when the bot just asked "المشكلة بتحصل باستمرار؟" a bare "لا" is an answer,
    not a refusal to talk. Without that flag, "لا" alone would hit DENY but
    we'd still want to interpret it as an answer in context.
    """
    norm = normalize(text)
    if not norm:
        return IntentResult(Intent.DIAGNOSE)

    # When awaiting a yes/no, check answers first and short-circuit.
    if expecting_answer:
        for intent in (Intent.UNKNOWN_ANSWER, Intent.AFFIRM, Intent.DENY):
            for kw in _LEXICON[intent]:
                if kw in norm:
                    return IntentResult(intent, kw)

    # Otherwise go in a sensible priority order. Multi-word keywords first
    # would shadow short ones (e.g. "السلام عليكم" before "سلام").
    priority = [
        Intent.HOW_ARE_YOU,   # "ازيك" before any greeting catch-all
        Intent.GREETING,
        Intent.FAREWELL,
        Intent.THANKS,
        Intent.LIST_SYSTEMS,
        Intent.HELP,
    ]
    for intent in priority:
        for kw in sorted(_LEXICON[intent], key=len, reverse=True):
            if kw in norm:
                return IntentResult(intent, kw)

    # Default: treat as symptom description for the diagnosis flow.
    return IntentResult(Intent.DIAGNOSE)
