"""End-to-end smoke test.

Runs scripted conversations through the chatbot and prints both sides so we
can eyeball the behavior without spinning up the HTTP server.
"""

from __future__ import annotations

import json
from pathlib import Path

from catalog import FaultCatalog
from conversation import Chatbot


def run(bot: Chatbot, session_id: str, scripts: list[str]) -> None:
    print("=" * 70)
    for msg in scripts:
        print(f"USER → {msg}")
        out = bot.handle(session_id, msg)
        print(f"BOT  → {out['reply']}")
        # Show structured side data when present
        extra = {k: v for k, v in out.items() if k not in ("reply", "state")}
        if extra:
            print(f"      [meta] {json.dumps(extra, ensure_ascii=False)}")
        print(f"      [state: {out['state']}]")
        print()
    print()


catalog = FaultCatalog(Path(__file__).parent / "faults.json")
bot = Chatbot(catalog)

# 1) Pure social: greeting → how-are-you → farewell
run(bot, "s1", ["هاي", "ازيك", "باي"])

# 2) Help & list systems
run(bot, "s2", ["انت بتعمل ايه؟", "الانظمة اللي بتشخصها ايه؟"])

# 3) Symptom → diagnostic question loop → diagnosis
run(bot, "s3", [
    "صباح الخير",
    "العربية بتسخن في الزحمة",
    "أيوه",   # answer to "بتحصل باستمرار؟"
    "أيوه",   # answer to "زادت مع الوقت؟"
])

# 4) Ambiguous symptom → candidates shown
run(bot, "s4", ["لمبة منورة في العداد"])

# 5) Unparseable answer mid-diagnosis → bot re-asks
run(bot, "s5", [
    "الفرامل بتفصل",
    "يمكن",      # not a clean yes/no
    "أيوه",      # now valid
    "لا",
])

# 6) Unrelated input → graceful fallback
run(bot, "s6", ["ابن عمي بياكل فول"])
