# Architecture Decision Records

One page per significant decision. A decision is changed by writing a new ADR that supersedes the old one, never by
editing history.

| ADR | Decision | Status |
|---|---|---|
| [001](ADR-001-transport-http.md) | Agent delivers to ingest over HTTP; no message broker in the core | Accepted |
| [002](ADR-002-event-identity.md) | Event identity is `(source_id, spool_epoch, seq)`, not a content hash | Accepted |
| [003](ADR-003-delivery-guarantee.md) | At-least-once delivery, effectively-once database effects, bounded by the failure model | Accepted |
| 004 | Spool durability protocol | Planned (Day 19) |
| 005 | Backpressure and overflow policy | Planned (Day 19) |

## Template

```markdown
# ADR-NNN: Title
Status: Proposed | Accepted | Superseded by ADR-XXX | Rejected
Date: YYYY-MM-DD

## Context        — the problem and the constraints
## Options        — at least two, with trade-offs
## Decision       — what we chose
## Consequences   — what gets easier, what gets harder
## Failure modes  — how this choice can fail, and what happens then
## Verification   — the test or measurement that proves it holds
```
