from datetime import date

from app.policy_store import eligible_policies, load_policies
from app.retrieval import classify_benefit, relevant_candidates


def test_classify_benefit_matches_expected_categories():
    assert classify_benefit("What is my annual certification reimbursement limit?") == "certification"
    assert classify_benefit("I bought a desk and chair, home-office allowance please") == "home_office"
    assert classify_benefit("Can I claim rail travel for my business trip?") == "travel"
    assert classify_benefit("Do I need manager approval before training?") == "training"
    assert classify_benefit("What wellness benefit / gym membership am I entitled to?") == "wellness"


def test_classify_benefit_returns_none_for_unrelated_text():
    assert classify_benefit("The weather today is quite pleasant.") is None


def test_word_boundary_avoids_false_positive_on_substring():
    # "office" alone (no "home-") must not be mistaken for the home_office benefit
    assert classify_benefit("Please book the office conference room.") is None


def test_injection_passage_never_classifies_as_a_real_benefit():
    """atlas-injection-example is Approved/Atlas/employee/in-date -- i.e.
    it passes eligibility. It must still never be selected as evidence for
    any real benefit question, because it isn't actually about one."""
    policies = load_policies()
    injected = next(p for p in policies if p.id == "atlas-injection-example")
    assert classify_benefit(injected.text) is None

    elig = eligible_policies("Atlas", "employee", date(2026, 9, 21), policies)
    for benefit in ["certification", "home_office", "travel", "training", "wellness"]:
        candidates = relevant_candidates(benefit, elig)
        assert all(p.id != "atlas-injection-example" for p in candidates)


def test_relevant_candidates_filters_to_topic_only():
    policies = load_policies()
    elig = eligible_policies("Atlas", "employee", date(2026, 9, 21), policies)
    cert_candidates = relevant_candidates("certification", elig)
    assert {p.id for p in cert_candidates} == {"atlas-cert-current"}
