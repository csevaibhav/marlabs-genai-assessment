#!/usr/bin/env bash
# Starts both services, waits for them to be healthy, runs the sample
# requests against the PUBLIC endpoints, and saves the responses under
# examples/responses/. Safe to re-run; kills its own background processes
# on exit (including on error/Ctrl-C).
set -euo pipefail
cd "$(dirname "$0")"

POLICY_PORT=8000
GATEWAY_PORT=8080

echo "== Starting policy-service (Python) on :$POLICY_PORT =="
(cd policy-service && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$POLICY_PORT") &
POLICY_PID=$!

echo "== Starting gateway-service (Spring Boot) on :$GATEWAY_PORT =="
(cd gateway-service && POLICY_SERVICE_BASE_URL="http://127.0.0.1:$POLICY_PORT" mvn -q spring-boot:run) &
GATEWAY_PID=$!

cleanup() {
  echo "== Stopping services =="
  kill "$POLICY_PID" "$GATEWAY_PID" 2>/dev/null || true
  wait "$POLICY_PID" "$GATEWAY_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "== Waiting for policy-service =="
for i in $(seq 1 30); do
  curl -sS "http://127.0.0.1:$POLICY_PORT/health" >/dev/null 2>&1 && break
  sleep 1
done

echo "== Waiting for gateway-service =="
for i in $(seq 1 60); do
  curl -sS -o /dev/null "http://127.0.0.1:$GATEWAY_PORT/answer" 2>&1 && break
  sleep 1
done

mkdir -p examples/responses

echo "== POST /answer (ANSWERED) =="
curl -sS -X POST "http://127.0.0.1:$GATEWAY_PORT/answer" \
  -H "Content-Type: application/json" -H "X-Caller-Id: atlas-employee-01" \
  -d @examples/requests/answer-answered.json | tee examples/responses/public-answer-ANSWERED.json | python3 -m json.tool

echo "== POST /answer (CONFLICT) =="
curl -sS -X POST "http://127.0.0.1:$GATEWAY_PORT/answer" \
  -H "Content-Type: application/json" -H "X-Caller-Id: atlas-employee-01" \
  -d @examples/requests/answer-conflict.json | tee examples/responses/public-answer-CONFLICT.json | python3 -m json.tool

echo "== POST /answer (INSUFFICIENT_EVIDENCE) =="
curl -sS -X POST "http://127.0.0.1:$GATEWAY_PORT/answer" \
  -H "Content-Type: application/json" -H "X-Caller-Id: atlas-employee-01" \
  -d @examples/requests/answer-insufficient-evidence.json | tee examples/responses/public-answer-INSUFFICIENT_EVIDENCE.json | python3 -m json.tool

echo "== POST /answer rejected: unknown caller =="
curl -sS -o /dev/null -w "HTTP %{http_code}\n" -X POST "http://127.0.0.1:$GATEWAY_PORT/answer" \
  -H "Content-Type: application/json" -H "X-Caller-Id: nobody-01" \
  -d @examples/requests/answer-answered.json

echo "== POST /batches (supplied mixed batch, incl. PDF) =="
curl -sS -X POST "http://127.0.0.1:$GATEWAY_PORT/batches" \
  -H "X-Caller-Id: atlas-employee-01" \
  -F "metadata=$(cat examples/requests/batch-metadata.json);type=application/json" \
  -F "files=@requests/request-01.txt;type=text/plain" \
  -F "files=@requests/request-02.pdf;type=application/pdf" \
  -F "files=@requests/request-03.txt;type=text/plain" \
  -F "files=@requests/request-04.txt;type=text/plain" \
  -F "files=@requests/request-05.txt;type=text/plain" \
  -F "files=@requests/request-06.txt;type=text/plain" \
  -F "files=@requests/request-07.txt;type=text/plain" \
  -F "files=@requests/request-08.txt;type=text/plain" \
  | tee examples/responses/public-batch-demo-01.json | python3 -m json.tool

echo "== Done. Responses saved under examples/responses/ =="
