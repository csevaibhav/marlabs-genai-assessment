"""Internal FastAPI service. Not the public API -- Spring Boot is the only
caller. This service trusts tenant/role as given by its caller (Spring),
because Spring is the one that resolved X-Caller-Id via the caller
directory; this service never re-derives identity from request bodies or
document contents (see extraction.py's handling of embedded "SYSTEM
MESSAGE" text for why that boundary matters).
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .answer_engine import (
    DeterministicOfflineProvider,
    MalformedProviderOutput,
    ProviderTimeout,
    ProviderUnavailable,
    decide,
    generate_answer,
)
from .batch_processor import (
    BatchValidationError,
    ManifestEntry,
    UploadedFile,
    process_batch,
)
from .policy_store import eligible_policies, load_policies
from .retrieval import classify_benefit, relevant_candidates
from .schemas import BatchMetadataIn, InternalAnswerRequest, InternalAnswerResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("policy-service")

app = FastAPI(title="Marlabs Policy Service (internal)")

_POLICIES = load_policies()

# Overridable in tests via app.dependency_overrides / direct monkeypatch of
# this module attribute -- lets us exercise timeout/unavailable/malformed
# behaviour through the real HTTP layer without a real model provider.
_PROVIDER = DeterministicOfflineProvider()


def set_provider(provider) -> None:
    global _PROVIDER
    _PROVIDER = provider


@app.get("/health")
def health():
    return {"status": "ok", "policies_loaded": len(_POLICIES)}


@app.post("/internal/answer", response_model=InternalAnswerResponse)
def internal_answer(req: InternalAnswerRequest):
    # document/batch-id-free diagnostic logging only; never logs the
    # question text itself or policy passage contents by default.
    logger.info("answer request tenant=%s role=%s as_of=%s", req.tenant, req.role, req.as_of)

    if not req.question.strip():
        raise HTTPException(status_code=400, detail={"code": "INVALID_QUESTION", "message": "question must be non-empty"})

    benefit = classify_benefit(req.question)
    candidates = (
        relevant_candidates(benefit, eligible_policies(req.tenant, req.role, req.as_of, _POLICIES))
        if benefit
        else []
    )
    decision = decide(benefit, candidates)

    if decision.status == "ANSWERED":
        try:
            answer = generate_answer(_PROVIDER, decision)
        except ProviderTimeout as exc:
            raise HTTPException(status_code=504, detail={"code": "PROVIDER_TIMEOUT", "message": "model generation timed out"}) from exc
        except ProviderUnavailable as exc:
            raise HTTPException(status_code=503, detail={"code": "PROVIDER_UNAVAILABLE", "message": "model provider unavailable"}) from exc
        except MalformedProviderOutput as exc:
            raise HTTPException(status_code=502, detail={"code": "MALFORMED_OUTPUT", "message": "model provider returned malformed output"}) from exc
        return InternalAnswerResponse(
            status="ANSWERED",
            answer=answer,
            citations=[{"chunk_id": c.chunk_id, "quote": c.quote} for c in decision.citations],
        )

    if decision.status == "CONFLICT":
        return InternalAnswerResponse(
            status="CONFLICT",
            answer=None,
            citations=[{"chunk_id": c.chunk_id, "quote": c.quote} for c in decision.citations],
        )

    return InternalAnswerResponse(status="INSUFFICIENT_EVIDENCE", answer=None, citations=[])


@app.post("/internal/process-batch")
async def internal_process_batch(
    metadata: str = Form(...),
    files: List[UploadFile] = File(default_factory=list),
):
    try:
        meta = BatchMetadataIn.model_validate_json(metadata)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_METADATA", "message": "batch metadata is invalid"}) from exc

    logger.info(
        "process-batch batch_id=%s tenant=%s role=%s as_of=%s items=%d",
        meta.batch_id, meta.tenant, meta.role, meta.as_of, len(meta.documents),
    )

    entries = [ManifestEntry(document_id=d.document_id, filename=d.filename) for d in meta.documents]
    uploaded = [UploadedFile(filename=f.filename, content=await f.read()) for f in files]

    try:
        results = process_batch(meta.tenant, meta.role, meta.as_of, entries, uploaded, _PROVIDER)
    except BatchValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": "BATCH_VALIDATION_FAILED", "message": str(exc)}) from exc

    total = len(results)
    completed = sum(1 for r in results if r.processing_status == "COMPLETED")
    failed = total - completed

    return JSONResponse(
        {
            "batch_id": meta.batch_id,
            "summary": {"total": total, "completed": completed, "failed": failed},
            "results": [
                {
                    "document_id": r.document_id,
                    "processing_status": r.processing_status,
                    "extracted": r.extracted,
                    "field_evidence": r.field_evidence,
                    "policy": r.policy,
                    "review_required": r.review_required,
                    "issues": r.issues,
                    "duplicate_of": r.duplicate_of,
                    "error": r.error,
                }
                for r in results
            ],
        }
    )
