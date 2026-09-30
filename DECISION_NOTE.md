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


- Built during a same-day. Claude and GPT was used as a coding assistant for drafting implementation code, tests, documentation, and supporting repository structure. My contribution was to define the implementation approach, review and refine the generated code, make the architectural and design decisions, validate the policy-handling logic, review the test scenarios, and guide the overall implementation against the assessment requirements. I remained responsible for the final implementation and understanding of the code.

- Python service verification: The policy-service was run in the development environment and its full pytest suite (52 tests) was executed live, including the supplied 8-document batch against a running server.

- Java gateway verification: The gateway-service could not be compiled or run in the development environment because outbound access to Maven Central was blocked by network policy, preventing Spring Boot dependencies from being downloaded. The Java implementation was reviewed line-by-line and checked against the API contract, but mvn clean test has not yet been executed in an environment with Maven dependencies available. This remains the next verification step before relying on the gateway implementation.

- Known incomplete area: There is currently no test that exercises the gateway's own connect/read-timeout configuration against a genuinely slow policy-service. The policy-service's provider-timeout behavior is covered using controllable Python test doubles, but the end-to-end gateway timeout behavior remains to be verified.

- Unfinished work: The primary remaining work is to compile and run the Java gateway with Maven dependencies available, execute the complete end-to-end test flow, and address any issues identified during that verification.

- The Java service (gateway-service) was compiled and its full test suite run locally (mvn clean test, 25 tests, all passing) — including fixing one test bug in BatchControllerTest where the metadata part was being simulated as an uploaded file rather than a plain form field, which is a MockMvc testing quirk, not a production code issue (a real embedded Tomcat resolves a filename-less multipart part as a request parameter; MockMvc's mock environment doesn't replicate that, so the test needed MockPart instead of MockMultipartFile).