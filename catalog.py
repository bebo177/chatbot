"""Fault catalog + symptom matcher.

Loads the bilingual dataset, builds an index, and matches user symptoms.

Schema (per entry):
  fault_id, system,
  fault_ar, fault_en,
  user_symptoms (mixed AR + EN),
  base_confidence,
  questions: [{id, question_ar, question_en, answers}],
  final_diagnosis: {risk_level, can_drive,
                    recommended_fix_ar, recommended_fix_en}

Matching strategy:
  1. Token overlap on the normalized symptom phrases — fast first pass.
  2. RapidFuzz token_set_ratio for the survivors — handles word reordering
     and typos.
  3. Single best-matching symptom score per fault wins (no dedup needed
     since each entry is already a unique fault).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from normalize import normalize, tokens


@dataclass
class Fault:
    fault_id: str
    system: str
    fault_ar: str
    fault_en: str
    user_symptoms: list
    base_confidence: float
    questions: list
    final_diagnosis: dict
    _normalized_symptoms: list = field(default_factory=list)


@dataclass
class Match:
    fault: Fault
    score: float          # 0..100, RapidFuzz scale
    matched_symptom: str  # the dataset symptom that produced the score


class FaultCatalog:
    """In-memory index of all faults, queryable by symptom text."""

    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        self.faults = {}
        self._token_index = defaultdict(set)

        for entry in raw:
            fault = Fault(
                fault_id=entry["fault_id"],
                system=entry["system"],
                fault_ar=entry["fault_ar"],
                fault_en=entry["fault_en"],
                user_symptoms=entry["user_symptoms"],
                base_confidence=entry["base_confidence"],
                questions=entry["questions"],
                final_diagnosis=entry["final_diagnosis"],
                _normalized_symptoms=[normalize(s) for s in entry["user_symptoms"]],
            )
            self.faults[fault.fault_id] = fault
            for sym in fault._normalized_symptoms:
                for tok in tokens(sym):
                    self._token_index[tok].add(fault.fault_id)

    @property
    def systems(self):
        return sorted({f.system for f in self.faults.values()})

    def by_id(self, fault_id):
        return self.faults.get(fault_id)

    def search(self, query, top_k=5, min_score=55.0):
        """Return top_k Match objects ranked by relevance to `query`."""
        q_norm = normalize(query)
        q_tokens = tokens(query)
        if not q_tokens:
            return []

        # Stage 1: candidate faults — anyone sharing at least one token.
        candidates = set()
        for tok in q_tokens:
            candidates |= self._token_index.get(tok, set())
        if not candidates:
            candidates = set(self.faults.keys())

        # Stage 2: per-symptom fuzzy scoring.
        results = []
        for fid in candidates:
            fault = self.faults[fid]
            best_score = 0.0
            best_sym = ""
            extra_hits = 0
            for sym_norm, sym_orig in zip(fault._normalized_symptoms, fault.user_symptoms):
                score = fuzz.token_set_ratio(q_norm, sym_norm)
                if score > best_score:
                    best_score = score
                    best_sym = sym_orig
                if score >= 70:
                    extra_hits += 1

            # Small bonus when multiple symptoms light up.
            if extra_hits > 1:
                best_score = min(100.0, best_score + 2.0 * (extra_hits - 1))

            # Nudge by base_confidence so ties break toward more common faults.
            best_score += fault.base_confidence

            if best_score >= min_score:
                results.append(Match(fault=fault, score=best_score, matched_symptom=best_sym))

        results.sort(key=lambda m: m.score, reverse=True)
        return results[:top_k]
