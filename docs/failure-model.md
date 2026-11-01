# Failure model

Status: **draft — no guarantee is claimed yet.** Each in-scope row becomes `verified` only when its automated test
passes in CI (`docs/testing/failure-matrix.md`, Day 16).

## The guarantee (ADR-003)

> Every event admitted to an agent's durable spool is eventually stored exactly once in PostgreSQL, provided the
> agent's disk survives, every component eventually recovers, and the spool's configured capacity is not exceeded.
> Events dropped before admission are counted, never silent.

## Definitions

| Term | Exact meaning |
|---|---|
| **Admitted** | The record's group-commit `fdatasync()` returned successfully. Before this point the event may be lost, and it has not been reported as admitted. |
| **Stored** | The ingest transaction containing the event's row (in `events` or `rejected_events`) committed. |
| **Delivered** | The agent received a terminal per-event result (`stored`, `duplicate`, `conflict`, `rejected`) and its durable commit marker covers that `seq`. |
| **Dropped before admission** | Discarded by the overflow policy while admission was stopped; counted in `dropped_pre_admission_total`; never assigned a `seq`. |

## Assumptions

- Agent runs on Linux with a local filesystem that honours `fdatasync`/`fsync` (ext4/xfs, default mount options).
- PostgreSQL is a reliable store (durable commits; its own replication/backups are out of scope).
- Clocks are not trusted for correctness; they are used only for latency measurement and event-time analytics.
- Components eventually restart and the network eventually heals.

## In scope (each has a test)

| ID | Failure | Expected outcome | Status |
|---|---|---|---|
| F1 | Agent process crash during append | Torn tail truncated on recovery; every admitted seq stored | not_started |
| F2 | Agent crash after server commit, before commit-marker update | Resend → `duplicate`; no extra rows | not_started |
| F3 | Ingest crash before commit | Agent times out and resends; stored once | not_started |
| F4 | Response lost after commit | Ambiguous outcome → resend → `duplicate` | not_started |
| F5 | Network partition | Spool grows; backlog drains after heal; no loss | not_started |
| F6 | PostgreSQL unavailable | `503` → backoff → drain; no loss | not_started |
| F7 | Corrupt or torn spool tail | Bad record and tail truncated and counted; earlier records delivered | not_started |
| F8 | Spool full / `ENOSPC` | Admission stops; drops counted; nothing admitted lost; resumes when space frees | not_started |
| F9 | Poison event (schema-invalid) | Stored in `rejected_events`; rest of batch stored; no retry loop | not_started |
| F10 | Same key, different payload | `event_conflicts` row + metric; original row unchanged | not_started |
| F11 | Ingest overload | `429` backpressure; agent backs off; no loss; bounded memory | not_started |

Status values: `not_started` · `in_progress` · `implemented_unverified` · `verified` · `deferred`.

## Out of scope (not claimed)

| Failure | Why excluded | What would cover it |
|---|---|---|
| Power loss / loss of volatile disk cache | A process kill leaves the OS page cache intact, so it does not simulate power loss | Fault-injecting filesystem such as LazyFS (planned after MVP) |
| Edge disk destroyed | The spool is single-node by design | Replicating the spool to a second device |
| PostgreSQL data loss | Treated as a reliable store | PostgreSQL replication and backups |
| Spool capacity exceeded for longer than it can buffer | Capacity is finite | Larger spool, sampling; drops are counted |
| Events never admitted | Never promised | Visible via `dropped_pre_admission_total` |
| macOS hosts | `fsync` does not flush the drive cache without `F_FULLFSYNC` | Guarantee and benchmarks are stated for Linux only |

## Reconciliation (how "no loss, no duplicates" is checked)

After every chaos run, for each `(source_id, spool_epoch)`:

1. The set of seqs in `events` ∪ `rejected_events` (disjoint) equals `{1 .. max_admitted_seq}` — no gaps, no extras.
2. `count(*) = count(distinct key)` in `events`.
3. `event_conflicts` is empty unless the scenario injected a conflict.
