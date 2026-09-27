# Sync — assumptions and non-obvious decisions

Per `CLAUDE.md`: assumptions specific to this service, not shared ones (those
live in the root `CLAUDE.md`).

## Chunk size: 100 rows

`UpsertFactsRequest` messages are small (a handful of short strings per row),
so 100 keeps every request comfortably under any gRPC message-size default
while keeping the chunk count -- and therefore the retry surface -- low. The
biggest file (1,159 raw encounter rows) becomes 12 chunks (11 of 100, one of
59). `chunk_size` is a parameter on `run_sync`/`_sync_resource`, not a env
var, since nothing in the plan calls for tuning it per environment.

`chunk_number` is the 0-based index of the chunk within that resource's row
order as read from the CSV (not a running index across resources), which is
what lets a retried chunk resolve to the same `(run_id, resource_type,
chunk_number)` key on the Data Service side (CLAUDE.md decision #2) and be a
no-op instead of a duplicate.

## Retry/backoff: 4 attempts, 1s/2s/4s

Only `UpsertFacts` is retried (per the task) -- `StartSyncRun` and
`CompleteSyncRun` are one-shot; either failing outright fails the whole run,
since there's nothing sensible to retry into (no `run_id` yet, or the run
is already fully sent). Retryable gRPC codes: `UNAVAILABLE`,
`DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED` -- transient conditions where the
same chunk resent later has a real chance of landing. Everything else
(`INVALID_ARGUMENT`, etc.) is raised immediately with no retry, since a
retry can't fix a request that was wrong the first time.

4 total attempts with backoff 1s, 2s, 4s between them (~7s worst case per
chunk) is enough to ride out a Data Service restart or a brief network blip
without turning a real outage into a multi-minute hang before the run gives
up and reports `failed`.

## Malformed row vs. Data Service validation

Sync does a *light shape check* only, before a row is ever sent:

- all required columns present for that resource,
- non-blank `patient_id`,
- the resource's date column matches `YYYY-MM-DD`.

A row failing this check is never sent at all, so it can't show up in the
Data Service's own `sync_quarantine` (only the Data Service can write there
-- it's the only component with MySQL credentials). Sync counts and logs
these locally as "malformed" in its own run summary, separate from the
`accepted`/`rejected` counts `UpsertFactsResponse` reports.

Everything else is left to the Data Service on purpose (CLAUDE.md decision
#1): type parsing, whether a `patient_id` on a diagnosis/lab/encounter row
actually exists, ICD code validity, natural-key dedup (the P0231 duplicate
encounter), and hashing. In particular, a **blank `pcp_provider_name`** is
mapped through as `""`, never rejected -- the plan is explicit that "a
missing PCP name is not 'no PCP history'"; whether a patient still has PCP
history via their encounters is a Data Service/evaluator semantic call, not
a sync-time validation concern.

## Resource order

Patients, then diagnoses/labs/encounters. Not required by the contract (the
Data Service defers the FK check to `CompleteSyncRun`), just the sane load
order and cheap to keep even though it isn't load-bearing.

## `SourceAdapter` shape

`SourceAdapter.rows(resource_type) -> Iterator[tuple[str, dict[str, str]]]`:
called once per resource type, yields `(resource_type, raw_row)` pairs for
that resource in source order. `CsvAdapter` is the only implementation.
Echoing `resource_type` back in the tuple (rather than just yielding
`raw_row`) keeps the shape uniform with a hypothetical future adapter that
reads a mixed feed and dispatches multiple resource types out of one
underlying stream -- without needing a heavier plugin interface for what is,
today, one CSV reader.

## Data directory

No setting exists in `libs/common/settings.py` for where the CSVs live (out
of scope to add one there). Compose mounts them at `./data` -> `/app/data`,
which is `data` relative to the container's `/app` working directory, so
that's the default. Overridable with `SYNC_DATA_DIR` for local runs from a
different cwd; nothing else reads this env var.

## Local test environment note

The generated `libs/common/grpc_gen/dataservice_pb2*.py` files need
`protobuf>=5.28` and `grpcio>=1.66` (matching `pyproject.toml`) to import at
all -- older versions raise at import time (`runtime_version` mismatch /
"generated code depends on grpcio>=1.84.0"). This host's shared Python
started at `protobuf==4.23.2`/`grpcio==1.54.2`, too old for the stubs; it was
upgraded in the course of building this and other services (now
`protobuf==7.36.2`/`grpcio==1.84.0`), which is what `pyproject.toml` already
calls for. If a given host still has the older versions, either
`pip install -e .` (as `CLAUDE.md` describes) or install into an isolated
virtualenv (`pip install grpcio>=1.66 protobuf>=5.28 pydantic-settings>=2.6
pytest>=8.3`) before running these tests -- see `README.md`. This mismatch
isn't specific to sync; any service importing `libs/common/grpc_gen` hits it
on an unpatched host.
