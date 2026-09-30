from datetime import date

from app.policy_store import Policy, eligible_policies, load_policies


def test_loads_all_twelve_supplied_records():
    policies = load_policies()
    assert len(policies) == 12
    ids = {p.id for p in policies}
    assert "atlas-injection-example" in ids
    assert "atlas-cert-draft" in ids


def test_draft_records_are_never_eligible():
    policies = load_policies()
    elig = eligible_policies("Atlas", "employee", date(2026, 9, 21), policies)
    assert all(p.id != "atlas-cert-draft" for p in elig)


def test_effective_interval_includes_start_excludes_end():
    policies = load_policies()
    # atlas-cert-current: 2026-06-01 to 2027-01-01
    on_start = eligible_policies("Atlas", "employee", date(2026, 6, 1), policies)
    assert any(p.id == "atlas-cert-current" for p in on_start)

    just_before_end = eligible_policies("Atlas", "employee", date(2026, 12, 31), policies)
    assert any(p.id == "atlas-cert-current" for p in just_before_end)

    on_end_date = eligible_policies("Atlas", "employee", date(2027, 1, 1), policies)
    assert all(p.id != "atlas-cert-current" for p in on_end_date)
    # the successor record picks up exactly where the previous one ends
    assert any(p.id == "atlas-cert-future" for p in on_end_date)


def test_historical_record_excluded_once_superseded():
    policies = load_policies()
    elig = eligible_policies("Atlas", "employee", date(2026, 9, 21), policies)
    ids = {p.id for p in elig}
    assert "atlas-cert-historical" not in ids
    assert "atlas-cert-current" in ids


def test_tenant_and_role_isolation():
    policies = load_policies()
    atlas_contractor = eligible_policies("Atlas", "contractor", date(2026, 9, 21), policies)
    assert {p.id for p in atlas_contractor} == {"atlas-cert-contractor"}

    boreal_employee = eligible_policies("Boreal", "employee", date(2026, 9, 21), policies)
    ids = {p.id for p in boreal_employee}
    assert ids == {"boreal-cert-current", "boreal-home-office-current"}

    # A caller can never see another tenant's or role's records, even
    # though the corpus otherwise says similar things about them.
    assert "atlas-cert-current" not in ids


def test_unknown_tenant_yields_no_eligible_records():
    policies = load_policies()
    assert eligible_policies("Nowhere", "employee", date(2026, 9, 21), policies) == []


def test_reordering_or_duplicating_records_does_not_change_the_result():
    policies = load_policies()
    shuffled = list(reversed(policies)) + [policies[0]]
    a = {p.id for p in eligible_policies("Atlas", "employee", date(2026, 9, 21), policies)}
    b = {p.id for p in eligible_policies("Atlas", "employee", date(2026, 9, 21), shuffled)}
    assert a == b
