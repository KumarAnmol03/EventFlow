# ADR-003: At-least-once delivery with effectively-once database effects

Status: Accepted
Date: 2026-11-02

## Context

"Exactly-once delivery" across a network is not achievable in general: when a response is lost, the sender cannot
know whether the receiver acted. Any honest guarantee has to say what can repeat, where duplicates are absorbed, and
under which failures it holds.

## Options

**A. At-most-once.** Send once, never retry. Simple; loses data on any failure. Rejected.

**B. Claim "exactly-once".** Not provable end to end for this system; would not survive an interview question about
lost acknowledgements. Rejected.

**C. At-least-once delivery + idempotent persistence.** The agent retries until it gets a terminal answer; the server
stores each key at most once. Duplicates happen in transit and are absorbed at the database.

## Decision

**Option C**, stated with its bounds:

> Every event admitted to an agent's durable spool is eventually stored exactly once in PostgreSQL, provided the
> agent's disk survives, every component eventually recovers, and the spool's configured capacity is not exceeded.
> Events dropped before admission are counted, never silent.

Mechanisms: durable admission (spool `fdatasync`), resend until a terminal per-event result, server returns `200` only
after commit, primary key on `(source_id, spool_epoch, seq)` with `ON CONFLICT DO NOTHING`, commit marker advanced
only over a contiguous prefix of terminal results.

Wording rule: say "at-least-once delivery with effectively-once database effects". Never "exactly-once" or "zero loss"
without the conditions above.

## Consequences

- The guarantee covers database rows only. Any future side effect (e.g. sending a notification per event) is not
  covered and would need its own idempotency.
- Every claim on the README or resume must match the sentence above and `docs/failure-model.md`.

## Failure modes

Covered failures and exclusions are listed in `docs/failure-model.md`. The main exclusions: power loss / volatile
disk-cache loss (not simulated by process kills), destruction of the edge disk, and PostgreSQL data loss.

## Verification

All in-scope failure-matrix scenarios (F1–F11) end with: stored seqs per `(source_id, spool_epoch)` exactly equal
`{1..max_admitted}` across `events` ∪ `rejected_events`, `count(*) = count(distinct key)`, and no unexpected
`event_conflicts` rows.
