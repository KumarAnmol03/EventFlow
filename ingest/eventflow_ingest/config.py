"""Runtime configuration, read from environment variables."""

import os
from dataclasses import dataclass, field

DEFAULT_DATABASE_URL = "postgresql://eventflow:eventflow-dev@localhost:5432/eventflow"


@dataclass(frozen=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL
    # token -> source_id. Each agent has exactly one token, bound to exactly one source_id.
    agent_tokens: dict[str, str] = field(default_factory=dict)
    max_batch_events: int = 500


def parse_agent_tokens(raw: str) -> dict[str, str]:
    """Parse 'edge-01:token1,edge-02:token2' into {'token1': 'edge-01', 'token2': 'edge-02'}.

    Error messages name the entry's position, never its content, so tokens don't leak into logs.
    """
    tokens: dict[str, str] = {}
    for position, entry in enumerate(e.strip() for e in raw.split(",")):
        if not entry:
            continue
        source_id, sep, token = entry.partition(":")
        if not sep or not source_id or not token:
            raise ValueError(f"INGEST_AGENT_TOKENS entry #{position} must look like source_id:token")
        if token in tokens:
            raise ValueError(f"INGEST_AGENT_TOKENS entry #{position} reuses a token")
        tokens[token] = source_id
    return tokens


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        agent_tokens=parse_agent_tokens(os.environ.get("INGEST_AGENT_TOKENS", "")),
    )
