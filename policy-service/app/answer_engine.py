"""Decision logic (pure, deterministic) + a swappable "generation" seam.

Two things are kept deliberately separate:

1. decide(...) -- pure function, no I/O, no failure modes. Given the benefit
   and the candidate policies (already eligibility- and relevance-filtered),
   it always returns one of ANSWERED / INSUFFICIENT_EVIDENCE / CONFLICT plus
   the citations. This can never time out, never be "unavailable", and never
   produce malformed output, because it does no external work.

2. AnswerProvider.render(...) -- the "model double". Only called on the
   ANSWERED path, at most once, with a bounded timeout and no retries (per
   the assessment's dependency-failure rules). The default implementation is
   extractive and deterministic: it does not paraphrase or invent wording,
   it returns the verbatim approved passage text, so the answer is always
   trivially "supported" by its own citation. Test doubles
   (FakeTimeoutProvider / FakeUnavailableProvider / FakeMalformedProvider)
   swap in to exercise the technical-failure paths required by the spec,
   without touching decide()'s policy logic at all.

Keeping these separate is what lets tests assert "policy conflict" and
"provider timed out" are different, non-overlapping failure classes, which
the assessment explicitly asks for ("Keep technical failures separate from
policy findings").
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import List, Optional

from .policy_store import Policy
from .retrieval import BENEFIT_LABELS

AMOUNT_PATTERN = re.compile(r"INR\s*([\d,]+)", re.IGNORECASE)


def extract_amount(text: str) -> Optional[int]:
    match = AMOUNT_PATTERN.search(text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


@dataclass
class Citation:
    chunk_id: str
    quote: str


@dataclass
class Decision:
    status: str  # ANSWERED | INSUFFICIENT_EVIDENCE | CONFLICT
    benefit: Optional[str]
    citations: List[Citation] = field(default_factory=list)
    # Only meaningful when status == ANSWERED: the single agreed-upon
    # passage text the generation step will render from.
    source_text: Optional[str] = None


def decide(benefit: Optional[str], candidates: List[Policy]) -> Decision:
    if benefit is None or not candidates:
        return Decision(status="INSUFFICIENT_EVIDENCE", benefit=benefit, citations=[])

    citations = [Citation(chunk_id=p.id, quote=p.text) for p in candidates]

    # "Distinct key" per candidate: its stated INR amount if it has one,
    # otherwise its normalized text. Candidates agree if every key is equal;
    # any disagreement among *eligible, relevant, approved* policies is a
    # genuine, unresolved policy conflict -- the assessment explicitly
    # forbids inventing a precedence rule to pick a winner.
    def key_of(p: Policy):
        amount = extract_amount(p.text)
        return amount if amount is not None else p.text.strip().lower()

    distinct_keys = {key_of(p) for p in candidates}

    if len(distinct_keys) > 1:
        return Decision(status="CONFLICT", benefit=benefit, citations=citations)

    return Decision(
        status="ANSWERED",
        benefit=benefit,
        citations=citations,
        source_text=candidates[0].text,
    )


# ---------------------------------------------------------------------------
# Generation seam ("model double" / optional real provider)
# ---------------------------------------------------------------------------


class ProviderTimeout(Exception):
    pass


class ProviderUnavailable(Exception):
    pass


class MalformedProviderOutput(Exception):
    pass


class AnswerProvider:
    """Base interface for the generation step. render() may raise
    ProviderUnavailable, or return non-str/empty output (treated as
    malformed by the caller)."""

    def render(self, decision: Decision) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class DeterministicOfflineProvider(AnswerProvider):
    """The required offline model double. No network calls, no API key,
    fully reproducible. Extractive: returns the approved passage text
    verbatim, optionally prefixed with a short, fixed template naming the
    benefit -- never inventing facts not present in source_text."""

    def render(self, decision: Decision) -> str:
        label = BENEFIT_LABELS.get(decision.benefit, decision.benefit or "benefit")
        return f"Per the applicable approved policy for your tenant and role, {decision.source_text}"


def generate_answer(
    provider: AnswerProvider, decision: Decision, timeout_seconds: float = 2.0
) -> str:
    """Invoke provider.render(decision) at most once, under a bounded
    timeout, with no automatic retry. Raises ProviderTimeout /
    ProviderUnavailable / MalformedProviderOutput on failure; callers map
    these to a non-2xx dependency failure, distinct from a policy finding.
    """
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(provider.render, decision)
    try:
        result = future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        # Do not wait for the stray thread; this is the "no automatic
        # retry, bounded timeout" contract -- we give up on this attempt
        # and let the (possibly still-running) thread be reclaimed later.
        executor.shutdown(wait=False)
        raise ProviderTimeout("model generation exceeded the bounded timeout") from exc
    except ProviderUnavailable:
        executor.shutdown(wait=False)
        raise
    except Exception as exc:  # any other provider-internal error
        executor.shutdown(wait=False)
        raise ProviderUnavailable(f"provider raised an unexpected error: {exc}") from exc
    else:
        executor.shutdown(wait=False)

    if not isinstance(result, str) or not result.strip():
        raise MalformedProviderOutput("provider returned empty or non-string output")
    return result
