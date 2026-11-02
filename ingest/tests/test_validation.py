"""Validation rules from docs/contracts.md §1–3."""

import pytest
from conftest import DELETE, EPOCH, SOURCE, make_event

from eventflow_ingest.validation import (
    I64_MAX,
    EventKey,
    Rejected,
    RequestError,
    Valid,
    payload_validators,
    validate_batch,
)


def run(*events, caller=SOURCE, max_events=500):
    return validate_batch({"events": list(events)}, caller, max_events)


def test_valid_event_passes():
    [result] = run(make_event())
    assert isinstance(result, Valid)
    assert result.key == EventKey(SOURCE, int(EPOCH), 1)


def test_schema_files_load():
    assert ("detection", 1) in payload_validators()


# --- Request-level failures: the whole batch is refused -----------------------------------------


@pytest.mark.parametrize(
    "body",
    [None, [], {}, {"events": []}, {"events": "x"}, {"events": [make_event()], "extra": 1}],
)
def test_malformed_body_is_400(body):
    with pytest.raises(RequestError) as exc:
        validate_batch(body, SOURCE, 500)
    assert exc.value.status == 400


def test_too_many_events_is_400():
    events = [make_event(seq=i) for i in range(1, 4)]
    with pytest.raises(RequestError) as exc:
        run(*events, max_events=2)
    assert exc.value.status == 400


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_id": DELETE},
        {"source_id": "Edge_01"},  # uppercase / underscore not allowed
        {"spool_epoch": DELETE},
        {"spool_epoch": int(EPOCH)},  # must be a string, so JSON parsers can't round it
        {"spool_epoch": "0"},
        {"spool_epoch": "007"},
        {"spool_epoch": str(I64_MAX + 1)},
        {"seq": DELETE},
        {"seq": 0},
        {"seq": True},  # JSON true is not a number
        {"seq": 1.0},
        {"seq": "1"},
        {"seq": I64_MAX + 1},
    ],
)
def test_invalid_identity_fails_whole_request(overrides):
    with pytest.raises(RequestError) as exc:
        run(make_event(seq=1), make_event(**({"seq": 2} | overrides)))
    assert exc.value.status == 400


def test_non_object_event_is_400():
    with pytest.raises(RequestError):
        run(make_event(), "not-an-object")


def test_source_mismatch_is_401():
    with pytest.raises(RequestError) as exc:
        run(make_event(), caller="edge-02")
    assert exc.value.status == 401


def test_duplicate_key_within_batch_is_400():
    with pytest.raises(RequestError):
        run(make_event(seq=5), make_event(seq=5))


# --- Event-level failures: only that event is rejected -----------------------------------------


@pytest.mark.parametrize(
    ("overrides", "reason_contains"),
    [
        ({"event_type": DELETE}, "event_type"),
        ({"schema_version": 0}, "schema_version"),
        ({"event_time_ns": 1.5e18}, "event_time_ns"),
        ({"event_time_ns": -1}, "event_time_ns"),
        ({"payload": []}, "payload"),
        ({"unexpected": 1}, "unexpected"),
        ({"event_type": "unknown_type"}, "unknown event_type"),
        ({"schema_version": 99}, "unknown event_type"),
    ],
)
def test_bad_envelope_rejects_only_that_event(overrides, reason_contains):
    good, bad = run(make_event(seq=1), make_event(seq=2, **overrides))
    assert isinstance(good, Valid)
    assert isinstance(bad, Rejected)
    assert bad.key.seq == 2
    assert reason_contains in bad.reason
    assert bad.raw["seq"] == 2


@pytest.mark.parametrize(
    ("payload_change", "reason_contains"),
    [
        ({"confidence": 1.5}, "payload.confidence"),
        ({"bbox": [0.1, 0.2, 0.3]}, "payload.bbox"),
        ({"track_id": -1}, "payload.track_id"),
        ({"track_id": True}, "payload.track_id"),
        ({"color": "red"}, "payload"),
    ],
)
def test_payload_schema_violation_is_rejected(payload_change, reason_contains):
    event = make_event()
    event["payload"].update(payload_change)
    [result] = run(event)
    assert isinstance(result, Rejected)
    assert reason_contains in result.reason


def test_results_keep_input_order():
    events = [make_event(seq=s) for s in (3, 1, 2)]
    events[1]["payload"]["confidence"] = 2
    results = run(*events)
    assert [r.key.seq for r in results] == [3, 1, 2]
    assert [type(r) for r in results] == [Valid, Rejected, Valid]
