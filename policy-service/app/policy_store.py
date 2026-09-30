"""Loads and filters the policy corpus.

This module knows nothing about HTTP, extraction, or answer generation.
Its only job is: given a tenant, role, and as_of date, return the policy
records that are *eligible* to be used as evidence at all. Approval state,
tenant/role match, and the effective date window are pure metadata checks --
never influenced by the passage text itself (see classify_and_decide in
retrieval.py / answer_engine.py for why the passage text is never trusted
as instructions).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List

DATA_PATH = Path(__file__).parent / "data" / "policies.json"


@dataclass(frozen=True)
class Policy:
    id: str
    tenant: str
    role: str
    approval_state: str
    effective_from: date
    effective_to: date
    text: str


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def load_policies(path: Path = DATA_PATH) -> List[Policy]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    policies = []
    for rec in raw["records"]:
        policies.append(
            Policy(
                id=rec["id"],
                tenant=rec["tenant"],
                role=rec["role"],
                approval_state=rec["approval_state"],
                effective_from=_parse_date(rec["effective_from"]),
                effective_to=_parse_date(rec["effective_to"]),
                text=rec["text"],
            )
        )
    return policies


def eligible_policies(
    tenant: str, role: str, as_of: date, policies: List[Policy] | None = None
) -> List[Policy]:
    """Records eligible for this caller at this date.

    A record is eligible only if:
      - approval_state == "Approved" (Draft and any other state are excluded)
      - tenant matches exactly (case-sensitive; tenants are fixed synthetic values)
      - role matches exactly
      - effective_from <= as_of < effective_to (interval includes start, excludes end)

    Order of the input list never matters and is never relied upon: this
    function filters, it does not rank. The same result must hold when
    records are reordered, duplicated, or new ones are appended, per the
    assessment's "keep policy records separate from application logic"
    requirement.
    """
    if policies is None:
        policies = load_policies()
    return [
        p
        for p in policies
        if p.approval_state == "Approved"
        and p.tenant == tenant
        and p.role == role
        and p.effective_from <= as_of < p.effective_to
    ]
