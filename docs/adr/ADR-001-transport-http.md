# ADR-001: Deliver events over HTTP; no message broker in the core

Status: Accepted
Date: 2026-11-02

## Context

The edge agent must move events to a central PostgreSQL store across an unreliable network. The agent already keeps
every admitted event in a durable on-disk spool (ADR-004, planned) until the server confirms it. The question is
what sits between the agent and the database.

Requirements for v1: no loss of admitted events, no duplicate rows, backpressure when the server is saturated, and a
system small enough to build, test against an explicit failure matrix, and explain completely.

## Options

**A. Direct HTTP.** The agent POSTs batches to an ingest service, which returns `200` only after the database
transaction commits.
- Buffering during outages: provided by the edge spool.
- One durability hand-off (agent → database) with a single, explicit confirmation (`200` after commit).
- Backpressure: `429 Retry-After` from the server.
- Fewer moving parts to run, monitor, and fault-test.

**B. Message broker (RabbitMQ) between agent and ingest.**
- Adds independent buffering, competing consumers, and fan-out to several downstream consumers.
- Adds a second durability boundary: publisher confirms, mandatory routing / unroutable handling, queue type and
  replication, consumer ack semantics, safe retry/dead-letter hand-off. Each is a separate failure mode to design
  and test.
- Its main benefit here — buffering — duplicates what the spool already provides.

**C. Kafka.** Same trade-off as B with a heavier operational footprint; its log-replay strength is not a v1 requirement.

## Decision

**Option A.** The agent sends `POST /v1/events:batch`; the server replies `200` only after commit (`contracts.md` §3).
Retries live at the edge: the spool resends with exponential backoff and full jitter.

## Consequences

- Easier: one confirmation point; no broker topology to get wrong; the end-to-end guarantee is provable with fewer
  test cases.
- Harder: the ingest service must be reachable for data to move (the spool absorbs outages instead);
  no built-in fan-out to multiple consumers; scaling ingest means more stateless HTTP workers behind a load balancer.

## Failure modes

- Ingest down → agent receives errors/timeouts, spool grows, drains on recovery (failure matrix F3, F6).
- Response lost after commit → ambiguous outcome, agent resends, idempotent key absorbs it (F4).
- Ingest saturated → `429`, agent backs off (F11).
- Spool fills during a long outage → admission stops, upstream drops are counted (F8).

## Verification

Failure-matrix scenarios F3, F4, F6, F8, F11 pass with gap-free reconciliation (`docs/testing/failure-matrix.md`).

## Revisit when

A second independent consumer of the event stream is required, or a measurement shows the ingest path cannot absorb
reconnect storms from many agents. Record that as a new ADR with the measurement attached.
