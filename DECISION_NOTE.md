# Decision note

## The consequential design choice

The `/batches` item-level `policy` field is not a bespoke, simplified
lookup -- it's the exact same `decide()` + `generate_answer()` pipeline that
backs the public `/answer` endpoint (see `policy_service/app/batch_processor.py:_policy_shape`).
A batch item's benefit is classified from the submitted document text
instead of a natural-language question, then run through identical
eligibility, relevance, conflict-detection, and extractive-generation logic,
and returned in the identical `{status, answer, citations}` shape.

**Alternative rejected:** a separate, batch-specific "look up the limit for
this benefit" helper, returning a simpler shape (e.g. just the matched
policy IDs and amounts) tailored to what a reviewer skimming a batch report
needs. This would have been less code and arguably a more purpose-built
report format.

**Why the shared pipeline won instead:** the two rejected outcomes,
`INSUFFICIENT_EVIDENCE` and `CONFLICT`, and the reasoning about eligibility
and relevance behind them, are exactly the semantics the assessment asks
`/answer` to get right (approval state, tenant/role match, effective dates,
no invented precedence between conflicting approved records). Building that
logic twice -- once for live questions, once for batch review -- would have
meant two places that could silently disagree about whether, say, two
home-office records really do conflict at a given `as_of` date. One engine,
one set of tests, one citation contract.

**Main limitation this creates:** it also couples batch item processing to
the answer engine's own failure modes. If a real model provider were plugged
in (see the README's "Offline mode" section) and it timed out or returned
malformed output while answering the policy question for *one* batch item,
that raises the same `ProviderTimeout`/`ProviderUnavailable`/
`MalformedProviderOutput` exceptions the public endpoint raises -- and in the
batch path, `batch_processor._process_one` catches these and marks *that
item* `FAILED` with `error.code = "MODEL_GENERATION_FAILED"`, rather than
returning a partial result with `policy: null` and the rest of the item's
extraction intact. With the offline deterministic provider (the only one
wired in today) this path is unreachable in practice, since offline
extractive rendering doesn't fail -- but a real model integration would make
this a live tradeoff worth revisiting.

## Other things worth naming as limitations

- Benefit classification (`policy-service/app/retrieval.py`) is fixed
  keyword/phrase matching, not embeddings or an LLM call. It's deterministic,
  testable, and needs no network -- but a request using vocabulary outside
  the five known benefit patterns (e.g. "relocation", "sabbatical") comes
  back `INSUFFICIENT_EVIDENCE`/`benefit: null` even if a human would
  recognize what's being asked. Extending the corpus to a new benefit
  category means adding both a policy record and a pattern in
  `BENEFIT_PATTERNS`.
- The extraction layer only ever looks for one currency token, `INR`, and
  one amount format (`INR <digits>`). It doesn't attempt other currencies or
  written-out amounts ("eighteen thousand rupees").

## Time spent / unfinished work / AI assistance

*(Vaibhav: personalize this section with your actual times before
submitting -- these reflect the pairing session, not a claim about your own
effort. Say plainly, in your own words, what you did vs. what Claude
produced, since the follow-up interview explicitly expects you to explain
and modify this without AI help.)*

- Built in a single pairing session with Claude (Claude Code / Sonnet) under
  a same-day deadline; both services, the full test suite, the supplied
  synthetic dataset, and this documentation were drafted with AI assistance.
- **Not independently verified in the environment this was built in:** the
  Python service (`policy-service`) was run and its full pytest suite (52
  tests) executed live, including the actual supplied 8-document batch
  against a running server. The Java service (`gateway-service`) could
  **not** be compiled or run in that environment -- outbound access to Maven
  Central was blocked by network policy there, with no way to fetch
  Spring Boot's dependencies. The Java code was written carefully and
  reviewed line-by-line, but `mvn clean test` has not actually been executed
  against it. **Run that yourself before relying on it or submitting** --
  fixing whatever it surfaces is expected next-step work, not an unknown.
- Known incomplete area: no test currently exercises the gateway's own
  connect/read-timeout configuration actually firing against a genuinely
  slow policy-service (only the policy-service's own provider-timeout
  doubles are tested at the Python layer).
