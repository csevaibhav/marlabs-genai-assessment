import json
from datetime import date

import pytest

from app.batch_processor import (
    BatchValidationError,
    ManifestEntry,
    UploadedFile,
    process_batch,
    validate_manifest,
)


def _load_manifest(requests_dir):
    manifest = json.loads((requests_dir / "batch-manifest.json").read_text())
    entries = [ManifestEntry(document_id=d["document_id"], filename=d["filename"]) for d in manifest["documents"]]
    files = [UploadedFile(filename=e.filename, content=(requests_dir / e.filename).read_bytes()) for e in entries]
    return manifest, entries, files


# --- whole-batch (manifest) validation -------------------------------------


def test_duplicate_document_id_fails_whole_batch():
    entries = [ManifestEntry("dup", "a.txt"), ManifestEntry("dup", "b.txt")]
    files = [UploadedFile("a.txt", b"x"), UploadedFile("b.txt", b"y")]
    with pytest.raises(BatchValidationError):
        validate_manifest(entries, files)


def test_duplicate_filename_fails_whole_batch():
    entries = [ManifestEntry("doc-1", "same.txt"), ManifestEntry("doc-2", "same.txt")]
    files = [UploadedFile("same.txt", b"x")]
    with pytest.raises(BatchValidationError):
        validate_manifest(entries, files)


def test_missing_file_part_fails_whole_batch():
    entries = [ManifestEntry("doc-1", "a.txt"), ManifestEntry("doc-2", "b.txt")]
    files = [UploadedFile("a.txt", b"x")]  # b.txt never uploaded
    with pytest.raises(BatchValidationError):
        validate_manifest(entries, files)


def test_extra_file_part_fails_whole_batch():
    entries = [ManifestEntry("doc-1", "a.txt")]
    files = [UploadedFile("a.txt", b"x"), UploadedFile("unexpected.txt", b"y")]
    with pytest.raises(BatchValidationError):
        validate_manifest(entries, files)


def test_valid_manifest_passes():
    entries = [ManifestEntry("doc-1", "a.txt")]
    files = [UploadedFile("a.txt", b"x")]
    validate_manifest(entries, files)  # no raise


# --- full batch processing, using the actual supplied dataset -------------


def test_supplied_batch_end_to_end(requests_dir):
    manifest, entries, files = _load_manifest(requests_dir)
    results = process_batch("Atlas", "employee", date.fromisoformat(manifest["as_of"]), entries, files)

    by_id = {r.document_id for r in results}
    assert by_id == {f"request-0{i}" for i in range(1, 9)}
    # every submitted item -- including the failed one -- produced a result
    assert len(results) == 8


def test_exact_duplicate_is_flagged_but_still_processed_independently(requests_dir):
    manifest, entries, files = _load_manifest(requests_dir)
    results = {r.document_id: r for r in process_batch("Atlas", "employee", date.fromisoformat(manifest["as_of"]), entries, files)}

    dup = results["request-06"]
    original = results["request-01"]
    assert dup.duplicate_of == "request-01"
    assert original.duplicate_of is None
    # both still fully, independently processed
    assert dup.processing_status == "COMPLETED"
    assert dup.extracted == original.extracted


def test_empty_file_fails_without_affecting_other_items(requests_dir):
    manifest, entries, files = _load_manifest(requests_dir)
    results = {r.document_id: r for r in process_batch("Atlas", "employee", date.fromisoformat(manifest["as_of"]), entries, files)}

    assert results["request-08"].processing_status == "FAILED"
    assert results["request-08"].error["code"] == "EMPTY_FILE"
    # neighbours are unaffected
    assert results["request-07"].processing_status == "COMPLETED"
    assert results["request-01"].processing_status == "COMPLETED"


def test_summary_counts_match_completed_and_failed(requests_dir):
    manifest, entries, files = _load_manifest(requests_dir)
    results = process_batch("Atlas", "employee", date.fromisoformat(manifest["as_of"]), entries, files)
    completed = sum(1 for r in results if r.processing_status == "COMPLETED")
    failed = sum(1 for r in results if r.processing_status == "FAILED")
    assert completed == 7
    assert failed == 1
    assert completed + failed == len(results)


def test_prompt_injection_in_submitted_request_never_changes_tenant_or_role(requests_dir):
    """request-05 asks (in the submitted text) to be treated as Boreal /
    approved. The batch caller is Atlas/employee -- results must reflect
    Atlas policy only."""
    manifest, entries, files = _load_manifest(requests_dir)
    results = {r.document_id: r for r in process_batch("Atlas", "employee", date.fromisoformat(manifest["as_of"]), entries, files)}
    r5 = results["request-05"]
    assert r5.policy["citations"][0]["chunk_id"] == "atlas-cert-current"
    assert "999999" not in json.dumps(r5.policy)
    assert any("embedded instruction-like content" in i for i in r5.issues)


def test_ambiguous_amount_and_policy_conflict_are_distinguishable_conditions(requests_dir):
    manifest, entries, files = _load_manifest(requests_dir)
    results = {r.document_id: r for r in process_batch("Atlas", "employee", date.fromisoformat(manifest["as_of"]), entries, files)}

    ambiguous_amount = results["request-03"]  # ambiguous *input*
    conflicting_policy = results["request-02"]  # conflicting *policy*
    assert ambiguous_amount.extracted["amount"] is None
    assert ambiguous_amount.policy["status"] == "ANSWERED"  # policy itself is not in conflict

    assert conflicting_policy.extracted["amount"] == 14000  # input was not ambiguous
    assert conflicting_policy.policy["status"] == "CONFLICT"  # policy itself disagrees


def test_review_required_is_always_true(requests_dir):
    manifest, entries, files = _load_manifest(requests_dir)
    results = process_batch("Atlas", "employee", date.fromisoformat(manifest["as_of"]), entries, files)
    assert all(r.review_required is True for r in results)
