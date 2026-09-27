# Care Gap Engine — shared decisions & assumptions log

This file is the single source of truth for anything this build assumed or
decided beyond what "Care Gap Engine Backend MVP Plan.md" (repo root, one
level up) states explicitly. **Every sub-agent must read this file in full
before writing code**, and must record any new assumption it makes before
finishing — in its own service's `ASSUMPTIONS.md` (e.g.
`services/data_service/ASSUMPTIONS.md`), not by editing this file directly
(parallel agents editing the same file race). The orchestrator folds those
into this file between agent runs.

Do not contradict a decision recorded here without flagging it back to the
orchestrator — these are load-bearing for other services' code.

## Repo layout

- Everything lives under `ecares/` (this directory), per explicit user
  instruction — this is the monorepo root the plan calls `care-gap-engine/`.
- Each service is its own directory under `services/`, including a `ui`
  service added at the user's request. The plan itself scopes the frontend
  OUT of the MVP — `services/ui` is a deliberately minimal, read-mostly
  dashboard against the Worklist API, not a build-tooled SPA. Ponytail rung:
  static HTML/CSS/JS, no bundler, no framework, served by a one-file Python
  HTTP server container.
- Source CSVs live at `ecares/data/*.csv` (extracted from the repo's
  `data.zip`, one level up).

## Contract already fixed centrally — do not redesign

- `proto/dataservice.proto` is final for this MVP. It groups RPCs exactly as
  the plan's "gRPC contract" table does: interactive read, interactive
  write, bulk, and no RPC for the outbox relay (internal loop only).
- `seeds/programs/*.yaml` are copied verbatim from the plan.
- `pyproject.toml` at repo root already lists every dependency every service
  needs (fastapi, grpcio, sqlalchemy, aiokafka, redis, pandas, pytest, ...).
  Add a dependency here only if truly missing — check first.
- `libs/common/` is shared and already has: `settings.py` (env-driven config,
  incl. `AS_OF_DATE`, `DS_ROLES`, Kafka/Redis/MySQL/gRPC targets),
  `logging.py` (JSON logs, call `configure_logging(service_name)` once at
  startup), `request_id.py` (`get_request_id()`/`set_request_id()`,
  propagated over gRPC metadata key `x-request-id`), `grpc_client.py` (stub
  factories), `errors.py` (`AppError` + subclasses: `NotFoundError`,
  `VersionConflictError`, `IllegalTransitionError`, `ValidationError` — each
  carries the REST `http_status` and `code`), `roles.py`
  (`allowed_task_types(role)`), `dates.py` (`months_before`, `days_overdue`,
  `is_past`, `add_days` — calendar-month arithmetic, use this rather than a
  hand-rolled 182-day approximation). `libs/common/grpc_gen/` holds the
  compiled proto stubs (`dataservice_pb2`, `dataservice_pb2_grpc`) —
  regenerate with `make proto` if `proto/dataservice.proto` ever changes
  (it shouldn't, without flagging the orchestrator first).
  These are READ-ONLY for service agents — if one seems to be missing
  something you need, add the need to your `ASSUMPTIONS.md` rather than
  editing a shared file two agents might touch at once.

## Assumptions made so far (orchestrator)

1. **`UpsertFacts` uses a generic row, not per-resource typed messages.**
   `FactRow { map<string,string> fields }` plus a `resource_type` string.
   Sync's job is only to map CSV column names to canonical field names
   (documented per-resource below) and do light shape checks (row parses as
   a dict, resource_type is one of the four). The Data Service owns deep
   validation (types, FK-style checks like a diagnosis/lab/encounter
   referencing a known `patient_id`), hashing, persistence and writing
   `sync_quarantine` rows for anything it rejects — because only the Data
   Service holds MySQL credentials, quarantine has to be written by it, not
   by sync.
   - Canonical field names Data Service expects per `resource_type`:
     - `patients`: `patient_id, first_name, last_name, date_of_birth, gender, phone, language, pcp_provider_name`
     - `diagnoses`: `patient_id, icd_code, description, diagnosed_date`
     - `labs`: `patient_id, test_name, result_value, result_date`
     - `encounters`: `patient_id, specialty, encounter_date, provider_name`
   - These are the exact CSV headers already, so the sync mapper is close to
     an identity map; keep it as one anyway so a future non-CSV adapter
     (FHIR, deferred) only has to satisfy the same mapper output shape.

2. **Change detection uses one staging table per resource inside the Data
   Service**, keyed by `(run_id, resource_type, chunk_number)` so a retried
   chunk overwrite-replaces rather than duplicates (delete-then-insert for
   that key, not a running append). At `CompleteSyncRun`, the Data Service
   diffs staging against the live table by natural key, compares `row_hash`,
   upserts changed rows into the live table, and collects the set of
   `patient_id`s touched (directly, or via a changed diagnosis/lab/encounter
   row) to return as `changed_patient_ids` and to write into the `outbox`
   table as `patient.changed` events in the same transaction.

3. **`row_hash`** = a stable hash (sha256, hex) of the canonical field values
   for that natural key, so "changed" means "any mapped field differs",
   independent of column order.

4. **Local tooling**: `uv` and MySQL client are not installed on the host;
   Docker (with Compose) is. Treat Docker Compose as the source of truth for
   running/integration-testing the stack (`make up`, `make seed`,
   `make test` all run through Compose). Pure-logic unit tests (mapper,
   evaluator, state machine transition rules) should also run standalone
   with `pytest` — against the host's Python (3.10 available locally, so
   avoid 3.12-only syntax even though the Docker image and `pyproject.toml`
   target 3.12).

   **Run everything through `ecares/.venv`, never against the host's global
   `site-packages`.** An earlier pass here installed `protobuf`/`grpcio`
   into the global interpreter to satisfy the generated gRPC stubs, which
   silently broke the version constraints of unrelated tools already on this
   machine (`tensorflow-intel`, `google-api-core`, `googleapis-common-protos`,
   `proto-plus` all pin `protobuf<7`; the global interpreter briefly had
   `7.36.2`). The orchestrator reverted the global interpreter to its
   original `protobuf==4.23.2`/`grpcio==1.54.2` and created `ecares/.venv`
   with every dependency from `pyproject.toml` installed directly (not
   editable — `requires-python>=3.12` in `pyproject.toml` rejects an
   editable install under the host's 3.10; a plain `pip install <deps>`
   doesn't hit that check, and `pytest`'s `pythonpath = ["."]` setting makes
   the repo importable without one). **Every agent: use
   `ecares/.venv/Scripts/python.exe` (Windows) for any local pip
   install/pytest/ruff run. Never run `pip install` against the bare
   `python`/`python3` on PATH — that's the global interpreter and it is
   shared with unrelated software on this machine.** If a dependency is
   missing from the venv, install it into `.venv` specifically, and note the
   addition in your `ASSUMPTIONS.md` rather than editing `pyproject.toml`
   directly (still true per the point above).

5. **gRPC is synchronous (`grpcio`) on the server side** (Data Service),
   since it is one process serving straightforward request/response calls
   with no streaming in this contract. Clients may use the sync or asyncio
   stub as convenient — `libs/common/grpc_client.py` offers both.

6. **Role visibility**: `worklist_api` resolves `X-User-Role` to the allowed
   `task_type`s (`scheduler` → `["scheduling"]`, `clinical`/`admin` →
   `["scheduling", "referral"]`) and always sends that list to the Data
   Service as `RoleFilter.allowed_task_types`. The Data Service applies it in
   the SQL `WHERE`, never post-filters in Python — a disallowed filter must
   come back as an empty page, never an error.

7. **Idempotency key** for `SaveEvaluationResult` = `sha256(patient_id +
   ":" + snapshot_hash)`. The Data Service stores the last-applied key on
   `patient_eval_state` and returns `applied=false` (writing nothing) when it
   matches the incoming key.

8. **`tests/oracle.py` must NOT import engine code.** It is pandas run
   directly against the CSVs, independent of the evaluator, per the plan's
   verification section. If it imports the evaluator, it stops being a
   verification oracle.

9. **Program loading**: the plan lists "program loader" under `services/engine/`
   but also says definitions are "stored as data" and `GET /programs` reads
   them back — so the engine parses `seeds/programs/*.yaml` into
   `ProgramDefinition` messages (JSON-serialized) and calls the Data
   Service's `UpsertPrograms` RPC (added to the proto after the initial
   draft) to persist them, keyed by `(program_id, version)`, idempotently, on
   startup. The evaluator then reads active definitions back from the Data
   Service (`ListPrograms`, which the Data Service serves from its
   `programs:active` Redis cache) rather than re-reading the YAML file
   itself — that keeps "stored as data" true in a way a future admin action
   (deactivate a version) could actually change without a code change.

10. **Sync service, folded in from `services/sync/ASSUMPTIONS.md`**: chunk
    size 100 rows (chunk_number = 0-based index within that resource's row
    order, stable across retries); only `UpsertFacts` is retried (4 attempts,
    1s/2s/4s backoff, retryable codes `UNAVAILABLE`/`DEADLINE_EXCEEDED`/
    `RESOURCE_EXHAUSTED` only); sync's own validation is a light shape check
    only (required columns present, non-blank `patient_id`, date matches
    `YYYY-MM-DD`) — a row failing THIS check is never sent and is counted
    locally as "malformed" (distinct from the Data Service's own
    accepted/rejected counts, since only the Data Service can write
    `sync_quarantine`); resource load order is patients first (not
    load-bearing, just sane); an optional `SYNC_DATA_DIR` env var (default
    `data`, read directly by `services/sync`, NOT added to
    `libs/common/settings.py` since it's sync-specific) points at the CSV
    directory — Compose's `./data:/app/data` mount already matches the
    default.

11. **Engine, folded in from `services/engine/ASSUMPTIONS.md`** — the Data
    Service MUST match these for the two sides to integrate correctly:
    - **`SaveEvaluationResultRequest.next_eval_at` is only a candidate.** The
      engine has no visibility into existing tasks/snoozes (it's stateless
      per plan steps 1-4), so it sends the earliest of every
      `NeedResult.next_check_candidate` / `ProgramResult.tier_recheck_at` it
      computed, ignoring snoozes entirely — an EMPTY STRING when nothing in
      the evaluation carries a future trigger date at all (not a sentinel
      date). **The Data Service must take `min(engine's next_eval_at [if
      non-empty], any live declined-task snooze_until + 1 day for a key just
      evaluated)`** to get the real `patient_eval_state.next_eval_at`.
    - **Kafka `patient.changed` message shape**: the engine's consumer
      parses defensively (JSON value with a top-level `patient_id` key,
      else a bare JSON string value, else the message key as raw UTF-8
      bytes, else the raw value as a UTF-8 string) — so the simplest and
      most robust thing for the outbox relay to publish is a JSON object
      `{"patient_id": "P0001", ...}` as the message value, always also
      keyed by `patient_id` as the plan requires. Either shape works with
      the engine as built; prefer the explicit JSON-with-key form since
      it's the most self-describing and doesn't rely on the fallback chain.
    - Idempotency key is fully computed by the engine
      (`sha256(f"{patient_id}:{snapshot_hash}")`, using `snapshot_hash`
      exactly as returned by `GetPatientSnapshot`) and sent as-is in
      `idempotency_key` — the Data Service should compare it verbatim
      against `patient_eval_state.last_idempotency_key`, not recompute it.
    - P0087: real driver of "no PCP task" is the has-upcoming-visit rule
      (an upcoming PCP encounter on 2026-04-13), not the gap/cadence
      comparison — this patient is wellness `standard` tier (no diagnoses),
      not `high_priority`. The plan's narrative names the coincidental
      180-day gap in this patient's past-visit history, but the strict
      `>`-not-`>=` overdue boundary itself is real and generically verified
      elsewhere in the engine's tests, independent of this specific patient.
      Nothing to reconcile — the observable outcome the plan asserts (no PCP
      task) matches either way.
    - Tier/condition grammar confirmed against the real YAML: `no_result`
      and `default` are bare YAML scalars, not dict conditions;
      `diagnosis_prefix`/`any_diagnosis_prefix` matching is plain
      `str.startswith` (never a regex — `G47.3`'s dot is literal).

12. **gRPC error convention — FINAL, per `services/worklist_api/ASSUMPTIONS.md`.**
    The Data Service must raise gRPC errors this way so the API's mapping
    (already built and tested) works without changes:
    - **Preferred**: set trailing metadata `("code", "<value>")` where
      `<value>` is one of `libs.common.errors.NOT_FOUND` /
      `VERSION_CONFLICT` / `ILLEGAL_TRANSITION` / `VALIDATION_ERROR`
      (i.e. the literal strings `"not_found"`, `"version_conflict"`,
      `"illegal_transition"`, `"validation_error"`) — the API reads this
      first and maps it straight to the matching `AppError` subclass
      (404 / 409 / 422 / 422).
    - **Fallback** (if trailing metadata isn't set), the API maps the bare
      gRPC status code: `NOT_FOUND`->404, `ABORTED`->409,
      `FAILED_PRECONDITION`->422, `INVALID_ARGUMENT`->422. Anything else
      becomes a generic 500.
    - So: a stale `version` on a task mutation -> status `ABORTED` (or the
      `version_conflict` metadata) -> 409. An illegal state transition ->
      `FAILED_PRECONDITION` (or `illegal_transition`) -> 422. A task/patient
      not found, OR one that exists but the caller's role can't see -> gRPC
      `NOT_FOUND` (or `not_found`) -> 404 (never a 403 for hidden-by-role —
      that would leak existence).

13. **`/admin/sync` and `/admin/evaluate` gap — flagged by
    `worklist_api`, for the orchestrator to close, not a service agent.**
    The proto has no single RPC that runs an end-to-end CSV load, and no
    single-patient enqueue RPC, so as built: `POST /admin/sync` only
    records an empty ledger entry (`StartSyncRun`->`CompleteSyncRun`, zero
    `UpsertFacts` calls — no rows actually load through this endpoint,
    only through `make seed` / `docker compose run sync`), and
    `POST /admin/evaluate?patient_id=X` falls back to
    `EnqueueDuePatients` (enqueues every currently-due patient, not just
    X) with a `note` in the response saying so. **Orchestrator TODO**: wire
    `/admin/sync` to actually invoke `services/sync`'s `run_sync()` (it's
    an importable function in the same monorepo image — no proto change
    needed, no duplicated CSV logic) rather than leave it a no-op ledger
    entry, since the plan's endpoint table implies it actually runs the
    load.

14. **Data Service — complete**, folded in from `services/data_service/ASSUMPTIONS.md`. All five services are now built. Notable points for whoever writes integration tests:
    - Resolution-picking rule for closing a task (the plan admits this is
      ambiguous): a referral task closes `visit_found` the moment its
      specialty gets ANY visit (upcoming or past); otherwise an upcoming
      visit wins over a tier change, which wins over the generic
      `not_eligible` catch-all.
    - `FORBIDDEN` is mapped in the error convention but never actually
      raised — a task hidden by role always comes back `NotFoundError`/404,
      confirmed by test. Consistent with the plan.
    - Redis caching (generation-counter scheme) is now actually wired into
      `ListTasks`/`ListPatients`/`ListPrograms` (it existed but was dead
      code after the first pass — fixed). `GetPatient` is never cached.
    - The "20 parallel saves for one patient -> exactly one open task"
      concurrency guarantee is real only against real MySQL (`FOR UPDATE`
      is a no-op against SQLite, which the unit tests use) — this is
      exactly the kind of check the plan's Verification section wants run
      against the live Docker Compose stack, not something already proven
      by a unit test.
    - `ListTasksRequest.sort` is accepted but not wired to an alternate
      cursor order — deliberate cut, the plan's verification checks counts
      and role filters, not sort order.

15. **`/admin/sync` wiring — the orchestrator (not a service agent) closed
    this gap** (see #13): `services/worklist_api/routers/admin.py`'s
    `POST /admin/sync` now imports and calls `services.sync.main.run_sync`
    directly (an in-process function call within the same monorepo image —
    no subprocess, no proto change), so the endpoint actually loads the
    CSVs instead of writing an empty ledger entry. `POST /admin/evaluate`'s
    single-patient limitation (falls back to `EnqueueDuePatients`, touching
    every due patient, not just the one named) is left as documented in
    `services/worklist_api/ASSUMPTIONS.md` — fixing it for real needs a new
    proto RPC, which is a bigger change than this MVP needs for one
    admin-only convenience endpoint.

## Open items for the orchestrator to fold in

(Sub-agents: list anything you assumed here, in your own
`services/<name>/ASSUMPTIONS.md`, not in this section.)
