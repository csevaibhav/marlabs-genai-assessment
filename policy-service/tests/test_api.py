import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.answer_engine import AnswerProvider, DeterministicOfflineProvider, ProviderUnavailable


@pytest.fixture()
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def restore_default_provider():
    yield
    main.set_provider(DeterministicOfflineProvider())


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["policies_loaded"] == 12


def test_answer_endpoint_answered(client):
    r = client.post(
        "/internal/answer",
        json={"tenant": "Atlas", "role": "employee", "as_of": "2026-09-21", "question": "certification limit?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ANSWERED"
    assert body["citations"][0]["chunk_id"] == "atlas-cert-current"


def test_answer_endpoint_conflict(client):
    r = client.post(
        "/internal/answer",
        json={"tenant": "Atlas", "role": "employee", "as_of": "2026-09-21", "question": "home-office allowance?"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "CONFLICT"
    assert r.json()["answer"] is None


def test_answer_endpoint_insufficient_evidence(client):
    r = client.post(
        "/internal/answer",
        json={"tenant": "Atlas", "role": "employee", "as_of": "2026-09-21", "question": "gym wellness benefit?"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "INSUFFICIENT_EVIDENCE"
    assert r.json()["citations"] == []


def test_answer_endpoint_rejects_blank_question(client):
    r = client.post(
        "/internal/answer",
        json={"tenant": "Atlas", "role": "employee", "as_of": "2026-09-21", "question": "   "},
    )
    assert r.status_code == 400


class _FakeUnavailable(AnswerProvider):
    def render(self, decision):
        raise ProviderUnavailable("down")


def test_answer_endpoint_maps_provider_unavailable_to_non_2xx(client):
    main.set_provider(_FakeUnavailable())
    r = client.post(
        "/internal/answer",
        json={"tenant": "Atlas", "role": "employee", "as_of": "2026-09-21", "question": "certification limit?"},
    )
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "PROVIDER_UNAVAILABLE"


def test_process_batch_endpoint_with_supplied_dataset(client, requests_dir):
    manifest = json.loads((requests_dir / "batch-manifest.json").read_text())
    metadata = {
        "batch_id": manifest["batch_id"],
        "tenant": "Atlas",
        "role": "employee",
        "as_of": manifest["as_of"],
        "documents": manifest["documents"],
    }
    files = [
        ("files", (d["filename"], (requests_dir / d["filename"]).read_bytes()))
        for d in manifest["documents"]
    ]
    r = client.post("/internal/process-batch", data={"metadata": json.dumps(metadata)}, files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == {"total": 8, "completed": 7, "failed": 1}
    assert body["results"][7]["document_id"] == "request-08"
    assert body["results"][7]["processing_status"] == "FAILED"


def test_process_batch_endpoint_rejects_mismatched_manifest(client, requests_dir):
    metadata = {
        "batch_id": "bad-01",
        "tenant": "Atlas",
        "role": "employee",
        "as_of": "2026-09-21",
        "documents": [{"document_id": "d1", "filename": "expected.txt"}],
    }
    files = [("files", ("wrong-name.txt", b"hello"))]
    r = client.post("/internal/process-batch", data={"metadata": json.dumps(metadata)}, files=files)
    assert r.status_code == 400
