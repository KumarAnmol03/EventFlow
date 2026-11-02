import pytest

from eventflow_ingest.auth import AuthError, authenticate
from eventflow_ingest.config import parse_agent_tokens

TOKENS = {"tok-a": "edge-01", "tok-b": "edge-02"}


def test_parse_agent_tokens():
    assert parse_agent_tokens("edge-01:tok-a, edge-02:tok-b") == TOKENS
    assert parse_agent_tokens("") == {}


@pytest.mark.parametrize("raw", ["edge-01", "edge-01:", ":tok", "edge-01:x,edge-02:x"])
def test_parse_agent_tokens_rejects_bad_entries(raw):
    with pytest.raises(ValueError):
        parse_agent_tokens(raw)


def test_parse_agent_tokens_never_echoes_secrets():
    with pytest.raises(ValueError) as exc:
        parse_agent_tokens("edge-01:supersecret,edge-02:supersecret")
    assert "supersecret" not in str(exc.value)


def test_valid_token_maps_to_its_source():
    assert authenticate("Bearer tok-b", TOKENS) == "edge-02"
    assert authenticate("bearer tok-a", TOKENS) == "edge-01"


@pytest.mark.parametrize("header", [None, "", "tok-a", "Basic tok-a", "Bearer ", "Bearer nope"])
def test_bad_credentials(header):
    with pytest.raises(AuthError):
        authenticate(header, TOKENS)
