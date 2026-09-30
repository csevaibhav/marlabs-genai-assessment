"""Batch orchestration: manifest validation, per-document extraction,
duplicate detection, and per-item failure isolation.

One item's failure must never prevent independent items from being
processed -- so every per-document step below runs inside its own
try/except, and only a genuine whole-batch problem (bad manifest shape,
file parts that don't match it) raises BatchValidationError, which the
caller (Spring Boot, and defensively this service too) turns into a
non-2xx response for the *whole* batch.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from .answer_engine import (
    AnswerProvider,
    MalformedProviderOutput,
    ProviderTimeout,
    ProviderUnavailable,
    DeterministicOfflineProvider,
    decide,
    extract_amount,
    generate_answer,
)
from .extraction import EmptyFileError, UnreadableFileError, extract_fields, extract_text
from .policy_store import Policy, eligible_policies
from .retrieval import relevant_candidates


class BatchValidationError(Exception):
    """Whole-batch problem: bad manifest, or files that don't match it."""


@dataclass
class ManifestEntry:
    document_id: str
    filename: str


@dataclass
class UploadedFile:
    filename: str
    content: bytes


@dataclass
class ItemResult:
    document_id: str
    processing_status: str  # COMPLETED | FAILED
    extracted: Optional[dict]
    field_evidence: Optional[dict]
    policy: Optional[dict]
    review_required: bool
    issues: List[str]
    duplicate_of: Optional[str]
    error: Optional[dict]


def validate_manifest(entries: List[ManifestEntry], files: List[UploadedFile]) -> None:
    doc_ids = [e.document_id for e in entries]
    filenames = [e.filename for e in entries]
    if len(doc_ids) != len(set(doc_ids)):
        raise BatchValidationError("duplicate document_id values in manifest")
    if len(filenames) != len(set(filenames)):
        raise BatchValidationError("duplicate filename values in manifest")

    uploaded_names = [f.filename for f in files]
    if len(uploaded_names) != len(set(uploaded_names)):
        raise BatchValidationError("duplicate filenames among uploaded file parts")

    manifest_names = set(filenames)
    uploaded_set = set(uploaded_names)
    if manifest_names != uploaded_set:
        missing = manifest_names - uploaded_set
        extra = uploaded_set - manifest_names
        raise BatchValidationError(
            f"uploaded files do not match manifest entries (missing={sorted(missing)}, extra={sorted(extra)})"
        )


def _policy_shape(
    benefit: Optional[str], tenant: str, role: str, as_of: date, provider: AnswerProvider
) -> Optional[dict]:
    """Same decision the /answer endpoint would give for this benefit --
    reused verbatim so 'policy' in a batch result has exactly the public
    /answer response shape, as the spec requires."""
    if benefit is None:
        return None
    candidates = relevant_candidates(benefit, eligible_policies(tenant, role, as_of))
    decision = decide(benefit, candidates)
    if decision.status == "ANSWERED":
        try:
            answer = generate_answer(provider, decision)
        except (ProviderTimeout, ProviderUnavailable, MalformedProviderOutput):
            # A generation failure for one item's policy lookup is this
            # item's problem, not the whole batch's -- surfaced as a
            # processing failure for the item by the caller.
            raise
        return {
            "status": "ANSWERED",
            "answer": answer,
            "citations": [{"chunk_id": c.chunk_id, "quote": c.quote} for c in decision.citations],
        }
    if decision.status == "CONFLICT":
        return {
            "status": "CONFLICT",
            "answer": None,
            "citations": [{"chunk_id": c.chunk_id, "quote": c.quote} for c in decision.citations],
        }
    return {"status": "INSUFFICIENT_EVIDENCE", "answer": None, "citations": []}


def process_batch(
    tenant: str,
    role: str,
    as_of: date,
    entries: List[ManifestEntry],
    files: List[UploadedFile],
    provider: Optional[AnswerProvider] = None,
) -> List[ItemResult]:
    validate_manifest(entries, files)
    if provider is None:
        provider = DeterministicOfflineProvider()

    files_by_name: Dict[str, UploadedFile] = {f.filename: f for f in files}
    seen_hashes: Dict[str, str] = {}  # sha256 -> first document_id with that hash
    results: List[ItemResult] = []

    for entry in entries:
        try:
            results.append(
                _process_one(entry, files_by_name[entry.filename], tenant, role, as_of, seen_hashes, provider)
            )
        except Exception as exc:  # noqa: BLE001 - isolate this item only
            results.append(
                ItemResult(
                    document_id=entry.document_id,
                    processing_status="FAILED",
                    extracted=None,
                    field_evidence=None,
                    policy=None,
                    review_required=True,
                    issues=[],
                    duplicate_of=None,
                    error={"code": "PROCESSING_ERROR", "message": "An internal error occurred while processing this document."},
                )
            )
    return results


def _process_one(
    entry: ManifestEntry,
    upload: UploadedFile,
    tenant: str,
    role: str,
    as_of: date,
    seen_hashes: Dict[str, str],
    provider: AnswerProvider,
) -> ItemResult:
    digest = hashlib.sha256(upload.content).hexdigest()
    duplicate_of = seen_hashes.get(digest)
    if digest not in seen_hashes:
        seen_hashes[digest] = entry.document_id

    try:
        text = extract_text(upload.content, upload.filename)
    except EmptyFileError:
        return ItemResult(
            document_id=entry.document_id,
            processing_status="FAILED",
            extracted=None,
            field_evidence=None,
            policy=None,
            review_required=True,
            issues=[],
            duplicate_of=duplicate_of,
            error={"code": "EMPTY_FILE", "message": "Submitted file is empty."},
        )
    except UnreadableFileError:
        return ItemResult(
            document_id=entry.document_id,
            processing_status="FAILED",
            extracted=None,
            field_evidence=None,
            policy=None,
            review_required=True,
            issues=[],
            duplicate_of=duplicate_of,
            error={"code": "UNREADABLE_FILE", "message": "File could not be read as UTF-8 text or a text-based PDF."},
        )

    fields = extract_fields(text)
    issues = list(fields.issues)

    try:
        policy = _policy_shape(fields.benefit, tenant, role, as_of, provider)
    except (ProviderTimeout, ProviderUnavailable, MalformedProviderOutput):
        return ItemResult(
            document_id=entry.document_id,
            processing_status="FAILED",
            extracted=None,
            field_evidence=None,
            policy=None,
            review_required=True,
            issues=[],
            duplicate_of=duplicate_of,
            error={"code": "MODEL_GENERATION_FAILED", "message": "Policy answer generation failed for this item."},
        )

    if policy is not None:
        if policy["status"] == "ANSWERED":
            has_amount = any(extract_amount(c["quote"]) is not None for c in policy["citations"])
            if has_amount:
                issues.append(
                    "Policy answer states an annual limit only; it does not establish "
                    "remaining balance, expense eligibility, or a payable amount for this "
                    "specific request."
                )
            else:
                issues.append(
                    "Policy answer states a general rule/eligibility criterion only; it does "
                    "not confirm approval or reimbursement of this specific request."
                )
        elif policy["status"] == "CONFLICT":
            ids = ", ".join(c["chunk_id"] for c in policy["citations"])
            issues.append(f"Applicable policy has an unresolved conflict between approved records ({ids}).")
        elif policy["status"] == "INSUFFICIENT_EVIDENCE":
            issues.append(f"No approved policy evidence found for the identified benefit ({fields.benefit}).")

    return ItemResult(
        document_id=entry.document_id,
        processing_status="COMPLETED",
        extracted={
            "benefit": fields.benefit,
            "amount": fields.amount,
            "currency": fields.currency,
            "reference": fields.reference,
        },
        field_evidence=fields.field_evidence,
        policy=policy,
        review_required=True,
        issues=issues,
        duplicate_of=duplicate_of,
        error=None,
    )
