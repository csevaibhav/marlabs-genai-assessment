import pytest

from app.extraction import (
    EmptyFileError,
    UnreadableFileError,
    extract_fields,
    extract_text,
)


def test_extracts_all_fields_from_supplied_request_01(requests_dir):
    raw = (requests_dir / "request-01.txt").read_bytes()
    text = extract_text(raw, "request-01.txt")
    fields = extract_fields(text)
    assert fields.benefit == "certification"
    assert fields.amount == 18000
    assert fields.currency == "INR"
    assert fields.reference == "CERT-101"
    assert "INR 18000" in fields.field_evidence["amount"]
    assert not fields.issues


def test_extracts_from_text_based_pdf(requests_dir):
    raw = (requests_dir / "request-02.pdf").read_bytes()
    text = extract_text(raw, "request-02.pdf")
    fields = extract_fields(text)
    assert fields.benefit == "home_office"
    assert fields.amount == 14000
    assert fields.reference == "HOME-202"


def test_ambiguous_amount_stays_null_with_issue(requests_dir):
    raw = (requests_dir / "request-03.txt").read_bytes()
    fields = extract_fields(extract_text(raw, "request-03.txt"))
    assert fields.amount is None
    assert fields.currency is None
    assert any("more than one differing amount" in i for i in fields.issues)
    assert fields.benefit == "certification"


def test_missing_amount_stays_null_with_issue(requests_dir):
    raw = (requests_dir / "request-07.txt").read_bytes()
    fields = extract_fields(extract_text(raw, "request-07.txt"))
    assert fields.amount is None
    assert any("not provided" in i for i in fields.issues)
    assert fields.benefit == "training"


def test_embedded_instruction_text_is_flagged_not_obeyed(requests_dir):
    raw = (requests_dir / "request-05.txt").read_bytes()
    fields = extract_fields(extract_text(raw, "request-05.txt"))
    # the amount and benefit are still extracted as real submitted data ...
    assert fields.amount == 70000
    assert fields.benefit == "certification"
    # ... but the embedded "ignore the caller header" instruction is
    # surfaced as an issue, never acted upon (no caller/tenant fields exist
    # here at all -- extraction has no such fields to change).
    assert any("embedded instruction-like content" in i for i in fields.issues)


def test_zero_byte_file_raises_empty_file_error():
    with pytest.raises(EmptyFileError):
        extract_text(b"", "request-08.txt")


def test_non_utf8_bytes_raise_unreadable_file_error():
    with pytest.raises(UnreadableFileError):
        extract_text(b"\xff\xfe\x00bad-bytes-not-utf8", "broken.txt")


def test_corrupt_pdf_bytes_raise_unreadable_file_error():
    with pytest.raises(UnreadableFileError):
        extract_text(b"not a real pdf at all", "broken.pdf")


def test_missing_reference_is_null_with_issue():
    fields = extract_fields("I would like reimbursement for INR 5000 for a certification course.")
    assert fields.reference is None
    assert any("No reference number" in i for i in fields.issues)
