import copy

import pytest

SOURCE = "edge-01"
TOKEN = "test-token-edge-01"
EPOCH = "7212650312774612501"

_VALID_EVENT = {
    "source_id": SOURCE,
    "spool_epoch": EPOCH,
    "seq": 1,
    "event_type": "detection",
    "schema_version": 1,
    "event_time_ns": 1_793_520_000_123_456_789,
    "admitted_time_ns": 1_793_520_000_130_000_000,
    "payload": {
        "tracker_run_id": "r3",
        "track_id": 42,
        "class": "person",
        "confidence": 0.91,
        "bbox": [0.12, 0.40, 0.08, 0.22],
    },
}


def make_event(**overrides):
    """A valid detection event; pass field=value to change fields, or field=DELETE to drop one."""
    event = copy.deepcopy(_VALID_EVENT)
    for name, value in overrides.items():
        if value is DELETE:
            event.pop(name, None)
        else:
            event[name] = value
    return event


DELETE = object()


@pytest.fixture
def event():
    return make_event()
