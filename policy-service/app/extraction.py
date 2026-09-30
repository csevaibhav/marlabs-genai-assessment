"""Document extraction: turn raw file bytes into (benefit, amount, currency,
reference) plus a source quotation for every value we're confident about.

Design principle carried through this whole module: a missing or ambiguous
value becomes None (visible), never a guess. Two different amounts in one
document is not "pick one" -- it is null with an issue explaining why.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .retrieval import classify_benefit

REFERENCE_PATTERN = re.compile(r"Reference:\s*([^\s].*)", re.IGNORECASE)
AMOUNT_PATTERN = re.compile(r"\bINR\s*[\d,]+\b", re.IGNORECASE)
INJECTION_HINT_PATTERN = re.compile(
    r"system message|ignore (all|the) (prior|caller)|disregard (all|the) (prior|caller)",
    re.IGNORECASE,
)


class UnreadableFileError(Exception):
    """Raised when file bytes cannot be turned into text at all."""


class EmptyFileError(Exception):
    """Raised for a zero-byte submission."""


@dataclass
class ExtractionResult:
    text: str
    benefit: Optional[str] = None
    amount: Optional[int] = None
    currency: Optional[str] = None
    reference: Optional[str] = None
    field_evidence: Dict[str, str] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)


def extract_text_from_txt(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnreadableFileError("file is not valid UTF-8 text") from exc


def extract_text_from_pdf(raw: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(raw))
        pages_text = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise UnreadableFileError("file is not a readable PDF") from exc
    text = "\n".join(pages_text).strip()
    if not text:
        raise UnreadableFileError("PDF contains no extractable text (scanned/image-only PDFs are out of scope)")
    return text


def extract_text(raw: bytes, filename: str) -> str:
    if len(raw) == 0:
        raise EmptyFileError("submitted file is empty")
    if filename.lower().endswith(".pdf"):
        return extract_text_from_pdf(raw)
    return extract_text_from_txt(raw)


def extract_fields(text: str) -> ExtractionResult:
    result = ExtractionResult(text=text)

    # Benefit
    result.benefit = classify_benefit(text)
    if result.benefit is None:
        result.issues.append("Could not identify the requested benefit from the submitted text.")

    # Reference
    ref_match = REFERENCE_PATTERN.search(text)
    if ref_match:
        reference = ref_match.group(1).strip()
        result.reference = reference
        result.field_evidence["reference"] = ref_match.group(0).strip()
    else:
        result.issues.append("No reference number found in the submitted text.")

    # Amount + currency: collect every "INR <number>" occurrence. Exactly
    # one distinct value -> supported. Zero -> missing. More than one
    # distinct value -> ambiguous, left null, flagged for review.
    matches = AMOUNT_PATTERN.findall(text)
    distinct_values = sorted({m for m in matches}, key=lambda s: s)
    numeric_values = sorted({int(re.sub(r"[^\d]", "", m)) for m in matches})

    if len(numeric_values) == 0:
        result.issues.append("Requested amount was not provided in the submitted text.")
    elif len(numeric_values) == 1:
        result.amount = numeric_values[0]
        result.currency = "INR"
        # quote the first literal occurrence, verbatim
        quote_match = AMOUNT_PATTERN.search(text)
        result.field_evidence["amount"] = quote_match.group(0).strip()
        result.field_evidence["currency"] = quote_match.group(0).strip()
    else:
        result.issues.append(
            "Submitted text states more than one differing amount ("
            + ", ".join(str(v) for v in numeric_values)
            + "); left unresolved rather than guessed."
        )

    # Untrusted-content note: submitted text is never allowed to change
    # caller identity, tenant, or application behaviour. We don't try to
    # strip it -- we surface that it was seen and ignored, for reviewer
    # visibility.
    if INJECTION_HINT_PATTERN.search(text):
        result.issues.append(
            "Submitted text contains embedded instruction-like content (e.g. a fake "
            "'system message'); it was treated as inert data and had no effect on "
            "caller identity, tenant, or policy evaluation."
        )

    return result
