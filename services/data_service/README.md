# Data Service

The only component that holds MySQL credentials (per the plan). Every other
service (`worklist_api`, `engine`, `sync`, `scheduler`) talks to it exclusively
over the gRPC contract in `proto/dataservice.proto`. This process owns:

- The task state machine, with optimistic locking (`version`) and one open
  task per `(patient_id, program_id, specialty)` enforced by the `tasks`
  table's `uq_one_open_task` unique index.
- Sync staging, dedup and quarantine for `UpsertFacts`/`CompleteSyncRun`.
- `SaveEvaluationResult`'s diff-against-stored-tasks logic and the
  `next_eval_at` computation.
- Redis caching (`worklist:{generation}:{hash}` pages, `programs:active`) and
  the generation-counter invalidation bumped on every write.
- The outbox relay: an internal loop (no RPC surface) that publishes
  `outbox` rows to Kafka's `patient.changed` topic.
- Audit rows, written in the same transaction as every state change.

See `ASSUMPTIONS.md` in this directory for what was verified/fixed in this
pass, and the repo root's `Care Gap Engine Backend MVP Plan.md` and
`CLAUDE.md` for the full spec and cross-service contract this implements.

## Running the tests

All commands below use the repo's `.venv`, never the bare `python` on PATH
(see `CLAUDE.md` #4 — the global interpreter is shared with unrelated
software on this machine).

```
# from the ecares/ repo root
.venv/Scripts/python.exe -m pytest services/data_service -q
```

These are pure unit tests against an in-memory SQLite session (see
`tests/conftest.py`) or fully mocked Redis/gRPC calls — no MySQL, Redis or
Kafka needed to run them. `tasks.open_key`'s MySQL-only generated column and
its unique index are not exercised by SQLite; see `tests/conftest.py` and
`ASSUMPTIONS.md` for what that means for concurrency coverage.

Sanity-check the module loads cleanly (what the process entrypoint imports):

```
.venv/Scripts/python.exe -c "import services.data_service.main"
```

Lint:

```
.venv/Scripts/python.exe -m ruff check services/data_service
```

## Running the service itself

Only via Docker Compose (`docker compose up data-service`, or `make up`) —
it needs a live MySQL, Redis and Kafka. `ROLE=data-service` selects this
service in the monorepo's single-image dispatcher; `DS_ROLES` (comma
separated, default `interactive,bulk,relay`) controls whether the background
outbox-relay thread starts (the interactive/bulk RPC split is deployment-only
— every RPC is always registered).

## Environment variables

All read once via `libs/common/settings.py` (`Settings`), defaults shown:

| Variable | Default | Used for |
| --- | --- | --- |
| `ROLE` | `worklist-api` | Must be `data-service` to run this service |
| `DS_ROLES` | `interactive,bulk,relay` | Whether the outbox-relay thread starts (`relay`) |
| `AS_OF_DATE` | unset -> today | The date every rule/read is evaluated against |
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | `mysql` / `3306` / `care_gap` / `care_gap` / `care_gap` | SQLAlchemy connection |
| `REDIS_HOST` / `REDIS_PORT` | `redis` / `6379` | Worklist cache + `programs:active` |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | Outbox relay's Kafka producer |
| `KAFKA_TOPIC_PATIENT_CHANGED` | `patient.changed` | Outbox relay's publish topic |
| `KAFKA_TOPIC_DLQ` | `patient.changed.dlq` | Where a message goes after 3 failed publish attempts |
| `GRPC_HOST` / `GRPC_PORT` | `0.0.0.0` / `50051` | Where the gRPC server listens |
| `WORKLIST_CACHE_TTL_SECONDS` | `30` | TTL for cached `ListTasks`/`ListPatients` pages |
| `DEFAULT_DECLINE_SNOOZE_DAYS` | `90` | Default snooze length on `DeclineTask` when the caller doesn't send one |
| `PRIMARY_CARE_SPECIALTIES` | `PCP` | Specialties that never get a referral task |

Patient detail (`GetPatient`) is never cached, by design — see the plan's
"Redis" note under "How the pieces stay correct".
