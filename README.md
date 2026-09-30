# Marlabs GenAI Spring Boot Assessment -- Employee Policy & Reimbursement Triage

Two services:

- **`gateway-service`** (Spring Boot / Java 21): the only public surface. Owns caller
  context (resolves `X-Caller-Id` to a tenant + role), request validation, and the
  public response shape for `/answer` and `/batches`.
- **`policy-service`** (Python / FastAPI): internal-only. Owns document extraction,
  policy retrieval/eligibility, conflict detection, and answer generation (a
  deterministic offline "model double" -- no API key, no network call, fully
  reproducible). Never called directly by anything outside the gateway.

The gateway is a thin, validating proxy on purpose: every business decision
(what's eligible, what's relevant, what the citations are) lives in one place,
in Python, so it can't drift between two independently-evolving codebases.

## Prerequisites

- Java 21, Maven 3.9+ (for `gateway-service`)
- Python 3.11+ (for `policy-service`)
- `curl` (for the sample calls below)

## Startup

```bash
# 1. Policy service (internal, port 8000)
cd policy-service
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. Gateway service (public, port 8080), in a second terminal
cd gateway-service
mvn spring-boot:run
# or: POLICY_SERVICE_BASE_URL=http://127.0.0.1:8000 mvn spring-boot:run
```

Or run both plus the sample requests in one go:

```bash
./run-demo.sh
```

## Tests

```bash
# Python (52 tests: policy eligibility, retrieval/relevance, answer decisions,
# extraction, batch processing, API layer, provider-failure doubles)
cd policy-service
.venv/bin/python -m pytest tests/ -v

# Java (caller directory, request validation, both controllers via MockMvc
# with the policy-service client mocked at the boundary)
cd gateway-service
mvn test
```

## Offline mode

There is no "online mode" to turn off: `DeterministicOfflineProvider`
(`policy-service/app/answer_engine.py`) is the only answer-generation path
wired in by default, requires no API key, and is what both the app and the
tests run against. It's deliberately **extractive**: for an ANSWERED result it
returns the verbatim approved policy text (prefixed with a fixed template),
never a paraphrase, so the answer can never say something its own citation
doesn't already say. A real model integration was optional per the brief and
isn't wired in; the seam to add one is `AnswerProvider` in the same file --
implement `.render(decision)`, wire it in place of `DeterministicOfflineProvider`
in `main.py`, and the timeout/attempt-once/no-retry wrapper in
`generate_answer()` applies to it unchanged.

## Configuration

`gateway-service/src/main/resources/application.yml`:

| Key | Default | Meaning |
|---|---|---|
| `policy-service.base-url` | `http://localhost:8000` (env `POLICY_SERVICE_BASE_URL`) | Where the gateway calls the Python service |
| `policy-service.connect-timeout-ms` | 2000 | TCP connect timeout to policy-service |
| `policy-service.read-timeout-ms` | 5000 | Bounded read timeout for the whole call |

`policy-service` has no required configuration; `generate_answer(...,
timeout_seconds=2.0)` bounds the (offline, normally-instant) generation step
itself, independent of the gateway's HTTP timeout.

## Sample API calls

```bash
# Policy question -> ANSWERED
curl -X POST http://localhost:8080/answer \
  -H "Content-Type: application/json" -H "X-Caller-Id: atlas-employee-01" \
  -d '{"question":"What is my annual certification reimbursement limit?","as_of":"2026-09-21"}'

# Two approved, in-date, on-topic records disagree -> CONFLICT
curl -X POST http://localhost:8080/answer \
  -H "Content-Type: application/json" -H "X-Caller-Id: atlas-employee-01" \
  -d '{"question":"What is my home-office allowance?","as_of":"2026-09-21"}'

# No wellness policy exists in the corpus -> INSUFFICIENT_EVIDENCE
curl -X POST http://localhost:8080/answer \
  -H "Content-Type: application/json" -H "X-Caller-Id: atlas-employee-01" \
  -d '{"question":"What wellness benefit am I entitled to?","as_of":"2026-09-21"}'

# Batch intake: the supplied mixed batch (5 TXT, 1 PDF, 1 byte-identical
# duplicate, 1 zero-byte file)
curl -X POST http://localhost:8080/batches \
  -H "X-Caller-Id: atlas-employee-01" \
  -F 'metadata={"batch_id":"demo-01","as_of":"2026-09-21","documents":[{"document_id":"request-01","filename":"request-01.txt"},{"document_id":"request-02","filename":"request-02.pdf"},{"document_id":"request-03","filename":"request-03.txt"},{"document_id":"request-04","filename":"request-04.txt"},{"document_id":"request-05","filename":"request-05.txt"},{"document_id":"request-06","filename":"request-06.txt"},{"document_id":"request-07","filename":"request-07.txt"},{"document_id":"request-08","filename":"request-08.txt"}]};type=application/json' \
  -F "files=@requests/request-01.txt;type=text/plain" \
  -F "files=@requests/request-02.pdf;type=application/pdf" \
  -F "files=@requests/request-03.txt;type=text/plain" \
  -F "files=@requests/request-04.txt;type=text/plain" \
  -F "files=@requests/request-05.txt;type=text/plain" \
  -F "files=@requests/request-06.txt;type=text/plain" \
  -F "files=@requests/request-07.txt;type=text/plain" \
  -F "files=@requests/request-08.txt;type=text/plain"
```

**Important about the `metadata` part:** send it as a literal inline value
(`-F 'metadata={...};type=application/json'`), not `-F metadata=@file.json`.
curl only omits the `filename` attribute on a part for the inline form, and
the gateway reads `metadata` as a plain multipart form field (`@RequestParam`),
not a file part -- with `@file.json` curl attaches a filename and the part
would (correctly) be rejected as an unexpected file part, since it isn't
listed in the manifest.

Saved, representative responses (captured live against the running
`policy-service`; see the note in `DECISION_NOTE.md` about what was and
wasn't verified against a live `gateway-service` in the environment this was
built in) are under `examples/responses/`.

## Response shapes

### `POST /answer` -- `{status, answer, citations}`

| status | answer | citations |
|---|---|---|
| `ANSWERED` | verbatim-extractive supported answer | the (agreeing) eligible quotations it's built from |
| `INSUFFICIENT_EVIDENCE` | `null` | `[]` |
| `CONFLICT` | `null` | the disagreeing eligible quotations |

`citations[].chunk_id` is the policy record ID; `.quote` is the verbatim
passage text.

### `POST /batches` -- `{batch_id, summary: {total, completed, failed}, results: [...]}`

`results` is in manifest order, one entry per submitted document_id, always
present even for failed/duplicate/empty items. Each entry:

```jsonc
{
  "document_id": "request-05",
  "processing_status": "COMPLETED",       // or "FAILED"
  "extracted": {                           // null if processing_status == FAILED
    "benefit": "certification",            // one of certification|home_office|travel|training|wellness, or null
    "amount": 70000,                       // null if missing or ambiguous (never guessed)
    "currency": "INR",                     // null alongside a null amount
    "reference": "CERT-505"                // null if no "Reference: ..." line found
  },
  "field_evidence": {                      // verbatim quote per *supported* extracted field; omits null fields
    "reference": "Reference: CERT-505",
    "amount": "INR 70000",
    "currency": "INR 70000"
  },
  "policy": {                              // exactly the /answer shape, for the identified benefit; null if
    "status": "ANSWERED",                  // processing failed or the benefit couldn't be identified
    "answer": "Per the applicable approved policy ...",
    "citations": [{"chunk_id": "atlas-cert-current", "quote": "..."}]
  },
  "review_required": true,                 // always true, every item
  "issues": [                              // human-readable review reasons: ambiguous input, policy
    "Submitted text contains embedded instruction-like content (e.g. a fake 'system message'); it was treated as inert data and had no effect on caller identity, tenant, or policy evaluation.",
    "Policy answer states an annual limit only; it does not establish remaining balance, expense eligibility, or a payable amount for this specific request."
  ],
  "duplicate_of": null,                    // earlier document_id with byte-identical file content, else null
  "error": null                            // null unless processing_status == FAILED: {code, message}
}
```

Rationale for this shape: `policy` reusing the exact `/answer` contract means
one decision engine, one set of tests, and one citation contract -- a batch
item's policy finding and a live question about the same benefit can never
silently disagree.

## Error codes

Both endpoints return `{"error": {"code": "...", "message": "..."}}` on any
non-2xx.

| HTTP | code | when |
|---|---|---|
| 400 | `MISSING_CALLER_ID` | `X-Caller-Id` header absent |
| 401 | `UNKNOWN_CALLER` | `X-Caller-Id` not in the caller directory |
| 400 | `MISSING_AS_OF` / `INVALID_AS_OF_DATE` | `as_of` absent / not valid `YYYY-MM-DD` |
| 400 | `INVALID_QUESTION` | `/answer`: `question` missing or blank |
| 400 | `INVALID_METADATA` | `/batches`: metadata part isn't valid JSON / missing `batch_id` |
| 400 | `EMPTY_MANIFEST` | `/batches`: `documents` is empty |
| 400 | `DUPLICATE_MANIFEST_ID` / `DUPLICATE_MANIFEST_FILENAME` | duplicate `document_id` / `filename` in the manifest |
| 400 | `DUPLICATE_FILE_PART` / `FILE_MANIFEST_MISMATCH` | duplicate upload, or uploads don't exactly match the manifest (missing or extra) |
| 400 | `MALFORMED_REQUEST` | request/multipart shape Spring itself couldn't bind |
| 502 | `DEPENDENCY_FAILURE` | policy-service reachable but returned an error (model timeout/unavailable/malformed output) |
| 503 | `DEPENDENCY_UNAVAILABLE` | policy-service unreachable |
| 500 | `INTERNAL_ERROR` | anything else unexpected (never leaks internals) |

Per-item failures inside a successful (200) batch response use a separate,
narrower set of item-level `error.code` values: `EMPTY_FILE`,
`UNREADABLE_FILE`, `MODEL_GENERATION_FAILED`, `PROCESSING_ERROR`. These are
deliberately distinct from the HTTP-level codes above -- an item failing
never changes the batch's own HTTP status.

## Repository layout

```
policy-service/        Python/FastAPI: extraction, policy retrieval, answer generation
gateway-service/       Spring Boot: public API, caller context, validation
requests/              The 12 policy passages (as data, not code) + the 8 synthetic request files + batch manifest
examples/               Sample request bodies and captured response JSON
run-demo.sh             Starts both services and runs the sample calls end-to-end
DECISION_NOTE.md         One consequential design choice, a rejected alternative, the main limitation, time spent, AI assistance
PRODUCTION_DESIGN_NOTE.md
```

## What the tests don't cover

- Load/concurrency behavior (the brief scopes this as a local, synchronous
  exercise; nothing here was tested under concurrent load).
- A real LLM integration path (optional per the brief; not built -- see
  "Offline mode" above for the seam that would carry one).
- OCR / scanned/image-only PDFs (explicitly out of scope; `extract_text_from_pdf`
  raises `UnreadableFileError` for a PDF with no extractable text layer).
- Non-ASCII / RTL currency or amount formats (the corpus and requests only
  ever use "INR <digits>"; the amount regex would need generalizing for other
  formats).
