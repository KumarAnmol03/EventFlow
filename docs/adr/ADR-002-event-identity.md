# ADR-002: Event identity is `(source_id, spool_epoch, seq)`

Status: Accepted
Date: 2026-11-02

## Context

Delivery is at-least-once (ADR-003): the same event can reach the server several times (retries, lost responses,
agent restarts). The database must store it once. That requires an identity that is

1. **stable** — every resend of one event carries the same key;
2. **unique** — two different real events never share a key;
3. **cheap** — computable at the edge with no coordination.

## Options

**A. Content hash** of selected fields, e.g. `SHA-256(camera_id | timestamp | track_id | kind)`.
Stable, but not unique: two genuine detections can share those fields (same timestamp, reused track id after a tracker
restart). A logical collision would silently drop a real event as a "duplicate".

**B. Random UUID per event.** Unique, and stable *if* it is generated once and stored with the event. Gives no
ordering, so loss cannot be detected by looking for gaps.

**C. Per-source sequence number assigned at durable admission**, plus a spool epoch.
Stable (stored in the spool record), unique (strictly increasing per spool), ordered, and gap-free by construction —
so a missing number *is* a lost event.

## Decision

**Option C.** Key = `(source_id, spool_epoch, seq)`.

- `seq` is assigned by the spool writer at admission and persisted inside the record (`contracts.md` §4).
- `spool_epoch` is a random 63-bit integer created when a spool directory is initialised. If a spool is lost and
  recreated, the new epoch guarantees old `seq` values are never reused.
- The server also stores `payload_sha256` to classify a repeated key as `duplicate` (same payload) or `conflict`
  (different payload — a producer bug, recorded in `event_conflicts`, never silently ignored).

## Consequences

- Loss detection becomes a set check: for each `(source_id, spool_epoch)`, stored seqs must equal `{1..max_admitted}`.
- Ordering per source comes for free.
- The key carries no domain meaning; domain identity (e.g. `tracker_run_id`, `track_id`) lives in the payload.
- Requires that `seq` assignment is correct across crashes: recovery resumes at last valid seq + 1.

## Failure modes

- Recovery bug resumes at a seq already used → same key, different payload → surfaces as a `conflict` (detected,
  counted), not as silent overwrite.
- Spool deleted without creating a new epoch → would reuse keys; prevented because `meta` (with the epoch) is created
  atomically with the spool directory, and the agent refuses to start on a spool without `meta`.

## Verification

- Unit: recovery after torn writes resumes at last valid seq + 1 (F7).
- End-to-end: gap-free reconciliation after every chaos scenario; conflict injection (F10) produces exactly one
  `event_conflicts` row and leaves the original row unchanged.
