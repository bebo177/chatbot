"""Conversation state machine.

States: IDLE → CHOOSING → DIAGNOSING → IDLE

The bot ALWAYS replies in Arabic regardless of input language.
Input symptoms can be Arabic or English — the catalog has both variants.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from catalog import FaultCatalog, Match
from intents import Intent, classify


class State(str, Enum):
    IDLE = "idle"
    CHOOSING = "choosing"
    DIAGNOSING = "diagnosing"


@dataclass
class Session:
    session_id: str
    state: State = State.IDLE
    candidate: Match = None
    pending: list = field(default_factory=list)
    question_idx: int = 0
    confidence: float = 0.0
    history: list = field(default_factory=list)


# All replies in Egyptian Arabic, regardless of input language.
_REPLIES = {
    Intent.GREETING: [
        "أهلاً بيك! 👋 أنا مساعدك لتشخيص أعطال العربية. قولي إيه اللي حاصل في عربيتك؟",
        "هاي! 🚗 احكيلي العربية بتعمل إيه وأنا أساعدك تشخص المشكلة.",
        "أهلاً! إنت في المكان الصح. وصفلي العَرَض اللي بتلاحظه — بالعربي أو الإنجليزي زي ما تحب.",
    ],
    Intent.HOW_ARE_YOU: [
        "تمام الحمد لله 🙏 إنت عامل إيه؟ في مشكلة في العربية محتاج تتطمن عليها؟",
        "كله تمام! قولي بقى — العربية فيها حاجة غريبة؟",
    ],
    Intent.FAREWELL: [
        "سلامات! 👋 أي وقت محتاج مساعدة في العربية أنا هنا.",
        "مع السلامة! خد بالك من نفسك وخد بالك من العربية. 🚗💨",
    ],
    Intent.THANKS: [
        "العفو! أي خدمة. 🙌",
        "تحت أمرك في أي وقت.",
    ],
    Intent.HELP: [
        "أنا بوت بشخّص أعطال السيارات. بشتغل على 5 أنظمة: ABS، التبريد، الكهرباء، الموتور، والفتيس.\n\n"
        "وصفلي العَرَض بالعربي أو بالإنجليزي زي ما تحب، مثلاً:\n"
        "  • \"العربية بتسخن في الزحمة\"\n"
        "  • \"لمبة ABS منورة\"\n"
        "  • \"check engine light on\"\n"
        "  • \"car won't start\"\n\n"
        "وأنا هخدك في تشخيص خطوة بخطوة.",
    ],
}


def _pick(intent):
    return random.choice(_REPLIES[intent])


def _format_diagnosis(match, final_confidence):
    """Render a finished diagnosis as a clean Arabic message."""
    d = match.fault.final_diagnosis
    risk_ar = {"low": "بسيطة", "medium": "متوسطة", "high": "خطيرة"}[d["risk_level"]]
    can_drive = ("متركبش العربية لحد ما تتصلح ⛔"
                 if d["can_drive"] == "no"
                 else "ممكن تسوقها بحذر لحد ما تتصلح ⚠️")

    fixes = "\n".join("  • " + fix for fix in d["recommended_fix_ar"])

    return (
        "✅ التشخيص النهائي\n"
        "─────────────────\n"
        "العطل: " + match.fault.fault_ar + "\n"
        "النظام: " + match.fault.system + "\n"
        "النسبة: " + str(int(final_confidence * 100)) + "%\n"
        "درجة الخطورة: " + risk_ar + "\n"
        "حالة القيادة: " + can_drive + "\n\n"
        "🔧 المقترح:\n" + fixes
    )


def _present_candidates(matches):
    """List the top few candidates for the user to pick."""
    lines = ["لقيت كذا احتمال — أيهم أقرب لحالتك؟ اكتب رقم:"]
    for i, m in enumerate(matches[:3], 1):
        lines.append("  " + str(i) + ". " + m.fault.fault_ar + " (" + m.fault.system + ")")
        lines.append("     العَرَض المسجل: \"" + m.matched_symptom + "\"")
    return "\n".join(lines)


class Chatbot:
    """Main entry point. Stateless across calls except for _sessions."""

    def __init__(self, catalog):
        self.catalog = catalog
        self._sessions = {}

    def _get_session(self, session_id):
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id=session_id)
        return self._sessions[session_id]

    def reset(self, session_id):
        if session_id in self._sessions:
            del self._sessions[session_id]

    def handle(self, session_id, user_text):
        session = self._get_session(session_id)
        session.history.append({"role": "user", "text": user_text})

        if session.state == State.DIAGNOSING:
            reply = self._handle_diagnosing(session, user_text)
        elif session.state == State.CHOOSING:
            reply = self._handle_choosing(session, user_text)
        else:
            reply = self._handle_idle(session, user_text)

        session.history.append({"role": "bot", "text": reply["reply"]})
        return reply

    # ──────────────────────────────────────────────────────────────────────

    def _handle_idle(self, session, text):
        result = classify(text)

        if result.intent in _REPLIES:
            return {"reply": _pick(result.intent), "state": session.state.value}

        if result.intent == Intent.LIST_SYSTEMS:
            systems_ar = {
                "ABS": "الفرامل (ABS)",
                "Cooling": "التبريد",
                "Electrical": "الكهرباء",
                "Engine": "الموتور",
                "Transmission": "الفتيس",
            }
            listed = "\n".join("  • " + systems_ar.get(s, s) for s in self.catalog.systems)
            return {
                "reply": "بشخّص أعطال في الأنظمة دي:\n" + listed + "\n\nقولي إيه اللي حاصل في عربيتك.",
                "state": session.state.value,
            }

        # Default: symptom description → run the matcher.
        matches = self.catalog.search(text, top_k=5)
        if not matches:
            return {
                "reply": "ملقيتش حاجة قريبة من اللي وصفته. جرّب توصف العَرَض بكلمات تانية — "
                         "مثلاً 'في صوت'، 'لمبة منورة'، 'العربية بتسخن'، أو قول 'help' علشان أوريك إيه اللي بشخّصه.",
                "state": session.state.value,
            }

        top = matches[0]
        # Decisive if there's only one candidate or the top is clearly ahead.
        decisive = len(matches) == 1 or (top.score - matches[1].score) >= 8
        if decisive:
            return self._start_diagnosis(session, top)

        session.state = State.CHOOSING
        session.pending = matches[:3]
        return {
            "reply": _present_candidates(matches),
            "state": session.state.value,
            "candidates": [
                {"fault_id": m.fault.fault_id, "fault_ar": m.fault.fault_ar, "system": m.fault.system}
                for m in matches[:3]
            ],
        }

    def _handle_choosing(self, session, text):
        """User saw 2–3 candidates and is picking one (by number) or refining."""
        from normalize import normalize as _norm

        norm = _norm(text)
        picked = None

        # Try to find a digit 1/2/3
        for ch in norm:
            if ch.isdigit():
                idx = int(ch) - 1
                if 0 <= idx < len(session.pending):
                    picked = session.pending[idx]
                break

        # Arabic-word ordinals fallback
        if picked is None:
            ordinals = {"الاول": 0, "اول": 0, "التاني": 1, "تاني": 1, "التالت": 2, "تالت": 2,
                        "first": 0, "second": 1, "third": 2}
            for word, idx in ordinals.items():
                if word in norm and idx < len(session.pending):
                    picked = session.pending[idx]
                    break

        if picked is not None:
            session.pending = []
            return self._start_diagnosis(session, picked)

        # Not a pick — treat as refined description.
        session.state = State.IDLE
        session.pending = []
        return self._handle_idle(session, text)

    def _start_diagnosis(self, session, match):
        session.state = State.DIAGNOSING
        session.candidate = match
        session.question_idx = 0
        session.confidence = match.fault.base_confidence

        intro = ("يلا نشوف. شكله " + match.fault.fault_ar +
                 " (" + match.fault.system + "). هسألك كام سؤال علشان أتأكد.")
        first_q = match.fault.questions[0]["question_ar"]
        return {
            "reply": intro + "\n\n" + first_q + "\n(جاوب بـ \"أيوه\" أو \"لا\" أو \"مش عارف\")",
            "state": session.state.value,
            "fault_id": match.fault.fault_id,
        }

    def _handle_diagnosing(self, session, text):
        questions = session.candidate.fault.questions
        current_q = questions[session.question_idx]

        # Parse the user's answer in "expecting_answer" mode.
        result = classify(text, expecting_answer=True)

        answer_key = None
        if result.intent == Intent.AFFIRM:
            answer_key = "أيوه"
        elif result.intent == Intent.DENY:
            answer_key = "لا"
        elif result.intent == Intent.UNKNOWN_ANSWER:
            answer_key = "مش عارف"

        if answer_key is None or answer_key not in current_q["answers"]:
            return {
                "reply": "معرفتش أفهم إجابتك. جاوبني بـ 'أيوه' أو 'لا' أو 'مش عارف'.\n\n"
                         + current_q["question_ar"],
                "state": session.state.value,
            }

        # Apply the confidence delta.
        delta = current_q["answers"][answer_key]
        session.confidence = max(0.0, min(1.0, session.confidence + delta))
        session.question_idx += 1

        if session.question_idx < len(questions):
            next_q = questions[session.question_idx]["question_ar"]
            return {
                "reply": next_q + "\n(جاوب بـ \"أيوه\" أو \"لا\" أو \"مش عارف\")",
                "state": session.state.value,
            }

        # Done — render diagnosis and reset.
        diagnosis_text = _format_diagnosis(session.candidate, session.confidence)
        fault_id = session.candidate.fault.fault_id
        confidence = session.confidence
        self.reset(session.session_id)
        return {
            "reply": diagnosis_text + "\n\nأي مشكلة تانية اقولّي.",
            "state": State.IDLE.value,
            "diagnosis": {
                "fault_id": fault_id,
                "confidence": round(confidence, 3),
            },
        }
