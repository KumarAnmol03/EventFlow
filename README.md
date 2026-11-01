# EventFlow

A fault-tolerant edge-to-database event pipeline: a C++17 edge agent durably spools events on disk and delivers
them over HTTP to a Python ingest service, which stores each one once in PostgreSQL.

> **Status: under construction (started 2026-11-01).** No reliability or performance claim is made until the tests
> and benchmarks that back it are in this repo. Target guarantee and its limits: [`docs/failure-model.md`](docs/failure-model.md).

## Design in one paragraph

Events are durably *admitted* to an append-only, CRC-checked spool on the edge device (`fdatasync` per group commit),
then sent in batches to `POST /v1/events:batch`. The server validates each event and stores the batch in one
transaction keyed by `(source_id, spool_epoch, seq)`, and replies `200` only after commit. The agent resends until it
gets a terminal answer, so delivery is at-least-once, and the primary key makes database effects effectively-once.

## Repository layout

```text
docs/        contracts, failure model, ADRs            (Day 1)
ingest/      Python ingest service                     (Days 2–5)
agent/       C++17 edge agent                          (Days 6–12)
tests/chaos/ end-to-end failure scenarios              (Days 13–16)
bench/       benchmarks and raw results                (Days 17–18)
```

## Quick start

Requires Docker (with Compose v2) and GNU Make.

```bash
make up      # start PostgreSQL and wait until healthy
make psql    # open a SQL shell
make down    # stop (keeps data); `make clean` also deletes data
make help    # all commands
```

## Documentation

- [Contracts](docs/contracts.md) — envelope, identity, batch API, spool format, schema
- [Failure model](docs/failure-model.md) — the guarantee, its assumptions, in/out of scope failures
- [Architecture decisions](docs/adr/README.md)
