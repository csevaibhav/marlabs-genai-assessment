"""Benefit classification: a small, explicit relevance gate on top of eligibility.

Eligibility (policy_store.eligible_policies) answers "is this record allowed
to be used for this caller at all". It says nothing about *topic*. Without a
relevance step, a naive implementation would hand every eligible record to
the generator for every question -- including atlas-injection-example, which
IS an Approved, in-date, Atlas/employee record. classify_benefit is what
keeps an eligible-but-off-topic (or actively adversarial) record out of the
candidate set, by requiring it to actually be about the benefit being asked
about.

Classification is intentionally simple keyword/phrase matching with word
boundaries (not naive substring search, which would e.g. match "certificate"
inside unrelated words, or match generic words like "allowance" that appear
in the injection passage). It is deliberately NOT an LLM call: relevance
filtering is a safety gate and must be deterministic and auditable.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional

from .policy_store import Policy

# Benefit key -> compiled pattern. Patterns match on word boundaries so
# "certification" doesn't also fire on unrelated words, and "home-office"
# requires the actual phrase rather than the bare word "office" or the
# generic word "allowance".
BENEFIT_PATTERNS: dict[str, re.Pattern] = {
    "certification": re.compile(r"\bcertif\w*", re.IGNORECASE),
    "home_office": re.compile(r"\bhome[\s-]?office\b|\bdesk\b|\bchair\b", re.IGNORECASE),
    "travel": re.compile(r"\btravel\b|\brail\b", re.IGNORECASE),
    "training": re.compile(r"\btraining\b", re.IGNORECASE),
    "wellness": re.compile(r"\bwellness\b|\bgym\b", re.IGNORECASE),
}

# Human-readable labels used when composing an answer string.
BENEFIT_LABELS = {
    "certification": "certification reimbursement",
    "home_office": "home-office allowance",
    "travel": "travel",
    "training": "training",
    "wellness": "wellness benefit",
}


def classify_benefit(text: str) -> Optional[str]:
    """Return the single benefit key the text is about, or None.

    If a text matched more than one benefit pattern this returns the first
    match in BENEFIT_PATTERNS iteration order (dict insertion order), which
    is deterministic. None of the supplied corpus or request text triggers
    more than one pattern, so this tie-break never actually fires today; it
    exists so behaviour stays defined if the corpus grows.
    """
    for key, pattern in BENEFIT_PATTERNS.items():
        if pattern.search(text):
            return key
    return None


def relevant_candidates(benefit: str, policies: Iterable[Policy]) -> List[Policy]:
    """Of the (already eligible) policies given, keep only ones on-topic for benefit."""
    return [p for p in policies if classify_benefit(p.text) == benefit]
