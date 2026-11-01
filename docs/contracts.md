# EventFlow contracts (v1)

Status: **draft** — becomes binding once the ingest service (Day 2–6) and the agent (Day 6–13) implement it.
Changing anything here requires an ADR in `docs/adr/`.

The system has four contracts:

1. [Event envelope](#1-event-envelope) — what one event looks like on the wire.
2. [Event identity](#2-event-identity) — how an event is uniquely and stably identified.
3. [Batch API](#3-batch-api) — how the agent hands events to the ingest service.
4. [Spool format](#4-spool-format-and-durability-protocol) — how the agent stores events on disk.

The database schema (§5) follows from 1–3.

---

## 1. Event envelope

JSON object, UTF-8. Generic: the ingest path never interprets `payload` beyond schema validation.

```json
{
  "source_id": "edge-07",
  "spool_epoch": "7212650312774612501",
  "seq": 18422,
  "event_type": "detection",
  "schema_version": 1,
  "event_time_ns": 1793520000123456789,
  "admitted_time_ns": 1793520000130000000,
  "payload": {
    "tracker_run_id": "r3",
    "track_id": 42,
    "class": "person",
    "confidence": 0.91,
    "bbox": [0.12, 0.40, 0.08, 0.22]
  }
}
```

| Field | Type | Rules |
|---|---|---|
| `source_id` | string | 1–64 chars, `[a-z0-9-]`. Must equal the source bound to the request's auth token. |
| `spool_epoch` | string (decimal) | Random 63-bit positive integer, fixed for the life of one spool. String so JSON parsers can't round it. |
| `seq` | integer | ≥ 1, assigned by the agent at spool admission, strictly increasing per `(source_id, spool_epoch)` with no gaps. |
| `event_type` | string | Registered type; selects the payload schema (`detection` in v1). |
| `schema_version` | integer | Version of the payload schema for this `event_type`. |
| `event_time_ns` | integer | When the event happened (source clock), Unix epoch nanoseconds. |
| `admitted_time_ns` | integer | When the agent durably admitted it (agent clock), Unix epoch nanoseconds. |
| `payload` | object | Validated against `ingest/schemas/<event_type>.v<schema_version>.json`. |

Unknown top-level fields are rejected (strict envelope); unknown payload fields follow the payload schema.

## 2. Event identity

**Key = `(source_id, spool_epoch, seq)`.** Never derived from the payload. See ADR-002.

- `seq` is written into the spool record at admission, so every resend of that record carries the same key.
- `spool_epoch` changes only when a spool is created from scratch, so a lost and recreated spool can never reuse an
  old key.
- The server stores `payload_sha256` = SHA-256 of the payload's canonical JSON (keys sorted, no insignificant
  whitespace, UTF-8). It is used only to tell *duplicates* from *conflicts*, never as identity.

| Incoming event vs stored row with same key | Classification |
|---|---|
| no stored row | `stored` |
| same `payload_sha256` | `duplicate` (expected after retries; counted) |
| different `payload_sha256` | `conflict` (producer bug; recorded in `event_conflicts`, stored row unchanged) |

## 3. Batch API

`POST /v1/events:batch`

- Header `Authorization: Bearer <agent token>`; each token maps to exactly one `source_id`.
- Body: `{"events": [ <envelope>, ... ]}`, 1–500 events.

**Success: `200 OK`** — returned **only after the database transaction has committed.**

```json
{
  "results": [
    {"seq": 18422, "status": "stored"},
    {"seq": 18423, "status": "duplicate"},
    {"seq": 18424, "status": "rejected", "reason": "payload.confidence: must be <= 1"}
  ]
}
```

One result per input event, same order. Every status is **terminal**: the agent may advance its commit marker past it.

| Response | Meaning | Agent action |
|---|---|---|
| `200` | Committed; per-event results | Advance commit marker over the contiguous prefix of results |
| `429` + `Retry-After` | Ingest saturated (backpressure) | Wait ≥ `Retry-After`, resend the same batch |
| `503` | Transient failure (e.g. database down) | Exponential backoff with full jitter, resend |
| `400` | Request malformed (not a single bad event) | Halt sending, raise alert metric — a bug, never retried blindly |
| `401` | Bad or missing token, or `source_id` mismatch | Halt sending, raise alert metric |
| timeout / connection reset | **Ambiguous** — may or may not have committed | Resend the same batch; the key makes it safe |

A single invalid event never fails the batch: it is returned as `rejected` and stored in `rejected_events`.
The exception is an event whose **identity fields** (`source_id`, `spool_epoch`, `seq`) are missing or invalid: it
cannot be keyed, and the agent always writes them, so the whole request is a bug → `400`.

## 4. Spool format and durability protocol

Linux only (see `failure-model.md`). Directory layout:

```text
spool/
  meta               spool_epoch, format version
  committed          last seq the server has confirmed (terminal result received)
  seg-<first_seq>.log  append-only segment files, <= 64 MiB each
```

**Record** (little-endian):

```text
| magic u32 | len u32 | crc32c u32 | seq u64 | payload (len bytes) |
```

- `crc32c` covers `seq ‖ payload`.
- `len` is bounds-checked against the remaining segment size before reading.

**Admission (group commit).** The writer thread takes up to N records or waits up to T ms, assigns consecutive
`seq`s, appends them with `write()`, calls `fdatasync()`, and only then reports them admitted. A record is
**admitted** exactly when its group's `fdatasync()` has returned successfully.

**Commit marker.** Write `committed.tmp` → `fsync` it → `rename` over `committed` → `fsync` the spool directory.

**Segment deletion.** Only after the durable committed seq ≥ the segment's last seq; then `fsync` the directory.

**Recovery.** Read `meta` and `committed`. Scan segments in order; stop at the first record with bad magic,
impossible `len`, short read, or CRC mismatch, and truncate the file there (counted in
`recovery_truncated_bytes`). Next `seq` = last valid + 1. Everything after `committed` is resent.

**Capacity.** When spool size reaches `max_spool_bytes`, or a write returns `ENOSPC`, admission stops until space is
freed. Events waiting upstream are subject to the overflow policy (default drop-oldest, counted in
`dropped_pre_admission_total`).

## 5. Database schema (draft)

The authoritative version will be `ingest/migrations/001_init.sql` (Day 2).

```sql
CREATE TABLE events (
  source_id        TEXT    NOT NULL,
  spool_epoch      BIGINT  NOT NULL,
  seq              BIGINT  NOT NULL,
  event_type       TEXT    NOT NULL,
  schema_version   INT     NOT NULL,
  event_time_ns    BIGINT  NOT NULL,
  event_time       TIMESTAMPTZ GENERATED ALWAYS AS (to_timestamp(event_time_ns / 1e9)) STORED,
  admitted_time_ns BIGINT  NOT NULL,
  stored_time_ns   BIGINT  NOT NULL,
  payload          JSONB   NOT NULL,
  payload_sha256   BYTEA   NOT NULL,
  PRIMARY KEY (source_id, spool_epoch, seq)
);

CREATE TABLE event_conflicts (
  source_id        TEXT   NOT NULL,
  spool_epoch      BIGINT NOT NULL,
  seq              BIGINT NOT NULL,
  existing_sha256  BYTEA  NOT NULL,
  incoming_sha256  BYTEA  NOT NULL,
  incoming_payload JSONB  NOT NULL,
  seen_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE rejected_events (
  source_id   TEXT   NOT NULL,
  spool_epoch BIGINT NOT NULL,
  seq         BIGINT NOT NULL,
  reason      TEXT   NOT NULL,
  raw         JSONB  NOT NULL,
  rejected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (source_id, spool_epoch, seq)
);
```

`event_time_ns` is the source of truth (nanoseconds); `event_time` exists for range queries (microsecond precision).

## Versioning

- Envelope changes → new API path (`/v2/...`).
- Payload changes → new `schema_version` for that `event_type`; old versions stay accepted until retired by ADR.
- Spool format changes → new `meta` format version; the agent refuses to open a spool with an unknown version.
