# Sync (`ROLE=sync`)

The Data Sync job. Runs once and exits (it's not a long-running server): reads
`patients.csv`, `diagnoses.csv`, `labs.csv` and `encounters.csv`, maps each
row to the canonical field names the Data Service expects, does a light
shape check, and sends the accepted rows to the Data Service over gRPC in
chunks via `StartSyncRun` -> `UpsertFacts` (repeated) -> `CompleteSyncRun`.

All real validation (types, patient FK checks, dedup on natural key),
hashing, persistence and quarantine happen in the Data Service — this job's
own failure mode is its own layer breaking (a missing/unreadable CSV, or
never reaching the Data Service at all), not individual rows getting
rejected, which is a normal partial-success outcome.

See `ASSUMPTIONS.md` for chunk size, retry/backoff parameters, and the
malformed-row-vs-Data-Service-validation split.

## Layout

- `adapters.py` — `SourceAdapter` protocol + `CsvAdapter`, the only
  implementation.
- `mappers.py` — one mapper function per resource (CSV row -> canonical
  field dict) plus the light shape check.
- `chunking.py` — splits a resource's rows into fixed-size, order-stable
  chunks (`chunk_number` has to be deterministic for gRPC-level retries).
- `main.py` — orchestration: `run_sync()` plus the `main()` entrypoint
  `run.py` calls when `ROLE=sync`.

## Running the tests

```bash
python -m pytest services/sync -q
```

From the repo root (`ecares/`), with dependencies installed per
`pyproject.toml` (`pip install -e .` or equivalent). The generated gRPC
stubs (`libs/common/grpc_gen`) need `grpcio>=1.66` and `protobuf>=5.28` to
import at all — if your interpreter has older versions, either
`pip install -e .` or install into a scratch virtualenv instead of
upgrading the shared one (see `ASSUMPTIONS.md`). No live Data Service or
MySQL needed — the gRPC stub is faked (`services/sync/tests/fake_stub.py`)
for every test except
`test_real_csvs.py`, which reads the actual `data/*.csv` files and is skipped
automatically if they're not present.

## Running it for real

Needs a reachable Data Service (`DATA_SERVICE_TARGET`, default
`data-service:50051`) and the four CSVs under `data/` relative to the
working directory (`SYNC_DATA_DIR` to override). Via Compose, this is
exactly what `make seed` (`docker compose run --rm sync`) does — the `sync`
service already mounts `./data:/app/data:ro` and sets `ROLE=sync`.

Standalone:

```bash
DATA_SERVICE_TARGET=localhost:50051 ROLE=sync python run.py
```

Exits `0` on a completed run (even with some rows rejected/quarantined by
the Data Service), `1` if the run itself failed. Prints a one-screen summary
at the end: per-resource accepted/rejected/malformed counts, total changed
patients, and the run id.
