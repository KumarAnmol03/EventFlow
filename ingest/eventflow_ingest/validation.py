"""Batch validation. See docs/contracts.md §1-3.

Two levels of failure, deliberately kept apart:

* Request-level (RequestError): the request cannot be processed at all -> the whole batch gets 400/401.
  Identity fields are checked here, because an event without a valid key cannot even be stored as rejected.
* Event-level (Rejected): one event is invalid -> only that event is rejected; the rest of the batch proceeds.
"""

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, ValidationError

I64_MAX = 2**63 - 1
SOURCE_ID_RE = re.compile(r"^[a-z0-9-]{1,64}$")
SPOOL_EPOCH_RE = re.compile(r"^[1-9][0-9]{0,18}$")  # decimal string, no leading zeros
SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
SCHEMA_FILE_RE = re.compile(r"^(?P<event_type>[a-z][a-z0-9_]*)\.v(?P<version>[1-9][0-9]*)\.json$")
MAX_REASON_CHARS = 500


class RequestError(Exception):
    """The whole request is invalid. `status` is the HTTP status to return (400 or 401)."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class EventKey:
    source_id: str
    spool_epoch: int
    seq: int


@dataclass(frozen=True)
class Valid:
    key: EventKey
    envelope: "Envelope"


@dataclass(frozen=True)
class Rejected:
    key: EventKey
    reason: str
    raw: dict[str, Any]


class Envelope(BaseModel):
    """The full event envelope. Strict: no type coercion, no unknown fields."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    source_id: str
    spool_epoch: str
    seq: int
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    schema_version: int = Field(ge=1)
    event_time_ns: int = Field(ge=0, le=I64_MAX)
    admitted_time_ns: int = Field(ge=0, le=I64_MAX)
    payload: dict[str, Any]


@cache
def payload_validators() -> dict[tuple[str, int], Draft202012Validator]:
    """Load every schemas/<event_type>.v<N>.json once. Adding an event type = adding a file."""
    validators = {}
    for path in sorted(SCHEMAS_DIR.glob("*.json")):
        match = SCHEMA_FILE_RE.match(path.name)
        if not match:
            raise RuntimeError(f"schema file name must be <event_type>.v<N>.json: {path.name}")
        schema = json.loads(path.read_text())
        Draft202012Validator.check_schema(schema)
        validators[(match["event_type"], int(match["version"]))] = Draft202012Validator(schema)
    return validators


def _is_int(value: Any) -> bool:
    # bool is a subclass of int in Python; JSON true/false must not pass as a number.
    return isinstance(value, int) and not isinstance(value, bool)


def parse_key(index: int, event: Any, caller_source_id: str) -> EventKey:
    """Extract and check the identity triple, or fail the whole request."""
    where = f"events[{index}]"
    if not isinstance(event, dict):
        raise RequestError(400, f"{where}: must be a JSON object")

    source_id = event.get("source_id")
    if not isinstance(source_id, str) or not SOURCE_ID_RE.match(source_id):
        raise RequestError(400, f"{where}.source_id: must match {SOURCE_ID_RE.pattern}")
    if source_id != caller_source_id:
        raise RequestError(401, f"{where}.source_id: token is not authorized for this source")

    epoch = event.get("spool_epoch")
    if not isinstance(epoch, str) or not SPOOL_EPOCH_RE.match(epoch) or int(epoch) > I64_MAX:
        raise RequestError(400, f"{where}.spool_epoch: must be a decimal string in 1..{I64_MAX}")

    seq = event.get("seq")
    if not _is_int(seq) or not 1 <= seq <= I64_MAX:
        raise RequestError(400, f"{where}.seq: must be an integer in 1..{I64_MAX}")

    return EventKey(source_id, int(epoch), seq)


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    location = ".".join(str(part) for part in err["loc"]) or "event"
    return f"{location}: {err['msg']}"


def validate_event(key: EventKey, event: dict[str, Any]) -> Valid | Rejected:
    """Validate one event whose identity is already known-good."""
    try:
        envelope = Envelope.model_validate(event)
    except ValidationError as exc:
        return Rejected(key, _first_error(exc)[:MAX_REASON_CHARS], event)

    validator = payload_validators().get((envelope.event_type, envelope.schema_version))
    if validator is None:
        reason = f"unknown event_type/schema_version: {envelope.event_type} v{envelope.schema_version}"
        return Rejected(key, reason[:MAX_REASON_CHARS], event)

    error = next(iter(sorted(validator.iter_errors(envelope.payload), key=lambda e: list(e.path))), None)
    if error is not None:
        location = ".".join(["payload", *(str(p) for p in error.path)])
        return Rejected(key, f"{location}: {error.message}"[:MAX_REASON_CHARS], event)

    return Valid(key, envelope)


def validate_batch(body: Any, caller_source_id: str, max_events: int) -> list[Valid | Rejected]:
    """Validate a decoded request body. Returns one result per event, in input order."""
    if not isinstance(body, dict) or set(body) != {"events"}:
        raise RequestError(400, 'body must be {"events": [...]}')
    events = body["events"]
    if not isinstance(events, list) or not 1 <= len(events) <= max_events:
        raise RequestError(400, f"events must be a list of 1..{max_events} items")

    # Pass 1: every identity must be valid and unique before any event is judged.
    keys = [parse_key(i, event, caller_source_id) for i, event in enumerate(events)]
    seen: set[EventKey] = set()
    for i, key in enumerate(keys):
        if key in seen:
            raise RequestError(400, f"events[{i}]: duplicate key within one batch")
        seen.add(key)

    # Pass 2: judge each event on its own.
    return [validate_event(key, event) for key, event in zip(keys, events, strict=True)]
