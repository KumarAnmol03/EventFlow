-- 001_init: core tables. See docs/contracts.md §5.

-- Accepted events. The primary key IS the idempotency mechanism:
-- a resent event has the same key, so it can never create a second row.
CREATE TABLE events (
    source_id        TEXT        NOT NULL,
    spool_epoch      BIGINT      NOT NULL CHECK (spool_epoch > 0),
    seq              BIGINT      NOT NULL CHECK (seq > 0),
    event_type       TEXT        NOT NULL,
    schema_version   INT         NOT NULL,
    event_time_ns    BIGINT      NOT NULL,   -- source of truth (nanoseconds)
    -- Derived, for range queries only. Microsecond precision at best (double rounding);
    -- never use it for identity or exact comparisons.
    event_time       TIMESTAMPTZ GENERATED ALWAYS AS (to_timestamp(event_time_ns / 1e9)) STORED,
    admitted_time_ns BIGINT      NOT NULL,   -- agent clock: when the spool fsync returned
    stored_time_ns   BIGINT      NOT NULL,   -- server clock: when the row was written
    payload          JSONB       NOT NULL,
    payload_sha256   BYTEA       NOT NULL CHECK (length(payload_sha256) = 32),
    PRIMARY KEY (source_id, spool_epoch, seq)
);

CREATE INDEX events_type_time ON events (event_type, event_time);

-- Same key arrived with a DIFFERENT payload: a producer bug. Recorded, never silently ignored.
-- No primary key on purpose: every occurrence is evidence.
CREATE TABLE event_conflicts (
    source_id        TEXT        NOT NULL,
    spool_epoch      BIGINT      NOT NULL,
    seq              BIGINT      NOT NULL,
    existing_sha256  BYTEA       NOT NULL,
    incoming_sha256  BYTEA       NOT NULL,
    incoming_payload JSONB       NOT NULL,
    seen_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX event_conflicts_key ON event_conflicts (source_id, spool_epoch, seq);

-- Events that failed validation. Keyed like events, so a resent bad event is stored once too.
CREATE TABLE rejected_events (
    source_id   TEXT        NOT NULL,
    spool_epoch BIGINT      NOT NULL CHECK (spool_epoch > 0),
    seq         BIGINT      NOT NULL CHECK (seq > 0),
    reason      TEXT        NOT NULL,
    raw         JSONB       NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, spool_epoch, seq)
);
