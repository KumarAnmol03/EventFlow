"""HTTP-level behaviour. TestClient is used without `with`, so the DB lifespan does not run."""

import pytest
from conftest import SOURCE, TOKEN, make_event
from fastapi.testclient import TestClient

from eventflow_ingest.api import app, get_settings
from eventflow_ingest.config import Settings

URL = "/v1/events:batch"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: Settings(agent_tokens={TOKEN: SOURCE})
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_missing_token_is_401(client):
    response = client.post(URL, json={"events": [make_event()]})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_wrong_token_is_401(client):
    response = client.post(URL, json={"events": [make_event()]}, headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


def test_invalid_json_is_400(client):
    response = client.post(URL, content=b"{not json", headers=AUTH)
    assert response.status_code == 400


def test_source_mismatch_is_401(client):
    response = client.post(URL, json={"events": [make_event(source_id="edge-99")]}, headers=AUTH)
    assert response.status_code == 401


def test_oversized_body_is_413(client):
    response = client.post(URL, content=b" " * (5 * 1024 * 1024 + 1), headers=AUTH)
    assert response.status_code == 413


def test_valid_batch_is_never_200_before_storage_exists(client):
    bad = make_event(seq=2)
    bad["payload"]["confidence"] = 9
    response = client.post(URL, json={"events": [make_event(seq=1), bad]}, headers=AUTH)
    assert response.status_code == 501
    assert response.json()["validated"] == {"valid": 1, "rejected": 1}
