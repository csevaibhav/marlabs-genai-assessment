import time
from datetime import date

import pytest

from app.answer_engine import (
    AnswerProvider,
    DeterministicOfflineProvider,
    MalformedProviderOutput,
    ProviderTimeout,
    ProviderUnavailable,
    decide,
    generate_answer,
)
from app.policy_store import eligible_policies, load_policies
from app.retrieval import classify_benefit, relevant_candidates

POLICIES = load_policies()


def _decide_for(tenant, role, as_of, question):
    benefit = classify_benefit(question)
    candidates = relevant_candidates(benefit, eligible_policies(tenant, role, as_of, POLICIES)) if benefit else []
    return decide(benefit, candidates)


def test_answered_when_exactly_one_relevant_eligible_record():
    d = _decide_for("Atlas", "employee", date(2026, 9, 21), "What is my certification reimbursement limit?")
    assert d.status == "ANSWERED"
    assert d.citations[0].chunk_id == "atlas-cert-current"


def test_insufficient_evidence_when_benefit_unidentifiable():
    d = _decide_for("Atlas", "employee", date(2026, 9, 21), "Can you help me with something unrelated?")
    assert d.status == "INSUFFICIENT_EVIDENCE"
    assert d.citations == []


def test_insufficient_evidence_when_benefit_known_but_no_policy_exists():
    d = _decide_for("Atlas", "employee", date(2026, 9, 21), "What wellness benefit / gym membership do I get?")
    assert d.status == "INSUFFICIENT_EVIDENCE"


def test_conflict_when_two_approved_records_disagree():
    d = _decide_for("Atlas", "employee", date(2026, 9, 21), "What is my home-office allowance?")
    assert d.status == "CONFLICT"
    assert d.answer is None if hasattr(d, "answer") else True
    ids = {c.chunk_id for c in d.citations}
    assert ids == {"atlas-home-office-a", "atlas-home-office-b"}


def test_conflict_citations_are_eligible_quotations_not_the_full_corpus():
    d = _decide_for("Atlas", "employee", date(2026, 9, 21), "What is my home-office allowance?")
    for c in d.citations:
        assert "home-office" in c.quote


def test_no_precedence_rule_invented_between_historical_and_current():
    """Historical/current/future certification records for the same tenant+role
    never coexist as eligible (date windows are disjoint) -- so this must
    resolve as ANSWERED from the single in-window record, not a conflict."""
    d = _decide_for("Atlas", "employee", date(2026, 3, 1), "certification limit?")
    assert d.status == "ANSWERED"
    assert d.citations[0].chunk_id == "atlas-cert-historical"


def test_deterministic_offline_provider_is_extractive_and_reproducible():
    d = _decide_for("Atlas", "employee", date(2026, 9, 21), "certification limit?")
    a1 = generate_answer(DeterministicOfflineProvider(), d)
    a2 = generate_answer(DeterministicOfflineProvider(), d)
    assert a1 == a2
    assert "INR 25000" in a1


# ---------------------------------------------------------------------------
# Controllable test doubles for provider failure modes
# ---------------------------------------------------------------------------


class FakeSlowProvider(AnswerProvider):
    def render(self, decision):
        time.sleep(0.5)
        return "too slow"


class FakeUnavailableProvider(AnswerProvider):
    def render(self, decision):
        raise ProviderUnavailable("simulated: provider is down")


class FakeMalformedProvider(AnswerProvider):
    def render(self, decision):
        return ""  # empty output is malformed


class FakeCrashingProvider(AnswerProvider):
    def render(self, decision):
        raise RuntimeError("simulated unexpected crash")


def test_provider_timeout_is_a_distinct_failure_from_policy_findings():
    d = _decide_for("Atlas", "employee", date(2026, 9, 21), "certification limit?")
    assert d.status == "ANSWERED"  # policy logic succeeded
    with pytest.raises(ProviderTimeout):
        generate_answer(FakeSlowProvider(), d, timeout_seconds=0.05)


def test_provider_unavailable_is_raised_distinctly():
    d = _decide_for("Atlas", "employee", date(2026, 9, 21), "certification limit?")
    with pytest.raises(ProviderUnavailable):
        generate_answer(FakeUnavailableProvider(), d)


def test_malformed_output_is_raised_distinctly():
    d = _decide_for("Atlas", "employee", date(2026, 9, 21), "certification limit?")
    with pytest.raises(MalformedProviderOutput):
        generate_answer(FakeMalformedProvider(), d)


def test_unexpected_provider_crash_is_treated_as_unavailable_not_silently_swallowed():
    d = _decide_for("Atlas", "employee", date(2026, 9, 21), "certification limit?")
    with pytest.raises(ProviderUnavailable):
        generate_answer(FakeCrashingProvider(), d)
