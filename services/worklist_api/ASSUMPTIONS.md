# Worklist API — assumptions and decisions

Everything here is scoped to `services/worklist_api/`. See the root
`CLAUDE.md` for cross-service assumptions; this file only records what this
service specifically decided, per its own instructions.

## gRPC error -> HTTP status mapping (critical for reconciliation)

`services/worklist_api/grpc_calls.py` has one `call()` wrapper that every
router uses to invoke the Data Service. It translates a `grpc.RpcError` into
the matching `libs.common.errors.AppError` subclass in two steps:

1. **Preferred**: read the `code` key out of the RPC's trailing metadata.
   `libs/common/errors.py`'s own docstring says gRPC carries the REST `code`
   via "`grpc.StatusCode` + trailing metadata", so if the Data Service sets
   trailing metadata `("code", "not_found" | "version_conflict" |
   "illegal_transition" | "validation_error")`, that string is looked up
   directly against `errors.NOT_FOUND` / `VERSION_CONFLICT` /
   `ILLEGAL_TRANSITION` / `VALIDATION_ERROR` and raised as the matching
   `AppError` subclass (with the same HTTP status those classes already
   carry: 404 / 409 / 422 / 422).
2. **Fallback**: if no `code` trailing-metadata key is present, fall back to
   a 1:1 mapping from the gRPC status code:
   - `NOT_FOUND` -> `NotFoundError` (404)
   - `ABORTED` -> `VersionConflictError` (409)
   - `FAILED_PRECONDITION` -> `IllegalTransitionError` (422)
   - `INVALID_ARGUMENT` -> `ValidationError` (422)
3. Anything else (both lookups miss) re-raises the original `grpc.RpcError`,
   which falls through to the app's catch-all `Exception` handler -> a
   generic 500 in the `{code, message, request_id}` shape.

**If the Data Service side does something different** (e.g. only sets the
gRPC status code and never trailing metadata, or uses different status
codes than the ones above), only the fallback table in `grpc_calls.py`
needs to change — the orchestrator should reconcile this table against
`services/data_service/ASSUMPTIONS.md` once that exists.

## Role header dependency: 422, not 401, for missing/invalid `X-User-Role`

The plan leaves this as "401 or 422, your call." This service raises
`errors.ValidationError` (422) via `deps.get_caller` for a missing or
unrecognized `X-User-Role` header, reusing the existing `AppError` subclass
rather than inventing a new one for a 401. Rationale: there is no
`AppError` subclass for 401 in `libs/common/errors.py`, and a malformed/
missing header is fundamentally a request-shape problem, which
`ValidationError` already models.

`X-User-Id` is optional; a missing one resolves to `user_id=""` and is not
rejected — no test or plan text requires it to be present.

Admin-only endpoints (`/admin/*`) additionally require `is_admin`, enforced
by `deps.require_admin`, which raises `errors.AppError(errors.FORBIDDEN, ...,
403)` — a flat 403 for a *valid but insufficient* role, distinct from the
422 above for a missing/invalid role, and distinct from the 404 used for a
task the caller's role may not see (never 403 there, so existence is never
leaked).

## Pagination: `limit` is rejected above 200, not clamped

`limit` is declared as `Annotated[int, Query(ge=1, le=200)]` on every list
endpoint (`/patients`, `/tasks`, `/admin/sync-runs`). FastAPI/Pydantic
reject an out-of-range value with 422 before any gRPC call is made — the
native framework validation, not a hand-rolled clamp. Default is 50 where
the plan doesn't specify.

## `/admin/sync` wiring

The proto has no single "run the CSV sync" RPC — `services/sync` is a
separate job that talks to the Data Service via `StartSyncRun` /
`UpsertFacts` / `CompleteSyncRun`. This service does **not** reimplement CSV
reading, mapping or chunking (that would duplicate `services/sync`'s job,
against the ladder). What `POST /admin/sync` actually does here:

```
StartSyncRun(source="csv") -> CompleteSyncRun(run_id, status="completed")
```

This records a sync run in the ledger (visible via `GET /admin/sync-runs`)
but **loads zero rows** — no `UpsertFacts` calls happen, so no facts change
and no patients are marked changed. It reflects "a run happened" (per the
task's own instruction for when the real re-sync entrypoint can't be
coordinated live) without faking data movement that didn't occur.

**Ideal wiring** for the orchestrator to reconcile: either (a) expose an
importable "run a sync end-to-end" function from `services/sync` (e.g.
`services.sync.run.run_once()`) that this endpoint calls in a background
task / subprocess, or (b) accept that `/admin/sync` in the MVP is only a
trigger-and-ledger-entry and the actual CSV load stays a `make seed` /
`docker compose run sync` operation, with the endpoint's response being
honest about which one happened (it currently is, via the empty
`changed_patient_ids`).

## `/admin/evaluate` wiring

The proto's bulk RPCs (`EnqueueDuePatients`, `EnqueueAllPatients`) are both
enqueue-for-later, and neither takes a `patient_id`. This endpoint:

- `all=true` -> `EnqueueAllPatients()`.
- `patient_id=<id>` -> **there is no single-patient enqueue RPC**, so this
  calls `EnqueueDuePatients(as_of_date=<effective as-of date>)` — the
  closest existing primitive, which enqueues every currently-due patient
  (not just the requested one). The response's `note` field says this
  explicitly so a caller isn't misled into thinking only that patient was
  touched.
- Exactly one of `patient_id` / `all=true` must be given, or the endpoint
  returns 422 before any gRPC call (`bool(patient_id) == bool(all)` check).

**Ideal wiring**: add a proto RPC like `EnqueuePatient(patient_id)` (or a
`repeated string patient_ids` field on `EnqueueDuePatientsRequest`) so a
single-patient re-check doesn't touch the whole due-patient set. Flagging
for the orchestrator/Data Service side to consider.

## `days_overdue`: computed here when the Data Service doesn't send it

`Task.days_overdue` on the wire is `optional int32`. `mapping.task_out()`
uses the Data Service's value when `HasField("days_overdue")` is true, and
otherwise computes it itself via `libs.common.dates.days_overdue(due_date,
settings.effective_as_of_date())` — matching the plan's "days overdue is
not stored, computed at read time" and giving a correct value either way
regardless of what the Data Service side ends up doing.

## Role visibility

`RoleFilter.allowed_task_types` is built once, in `mapping.role_filter()`,
always from `Caller.allowed_task_types` (itself from
`libs.common.roles.allowed_task_types(role)` — never reimplemented here,
never from a client-supplied value). Every list/get/mutation request builds
its `RoleFilter` through this one function. This service never filters
tasks after the fact in Python — visibility is only ever expressed in the
gRPC request, per the plan.

## Testing without a live Data Service

`services/worklist_api/tests/conftest.py` defines a `FakeStub` — a plain
Python object with the same method names as the generated
`DataServiceStub` (`GetMeta`, `ListTasks`, `CompleteTask`, ...), returning
canned `dataservice_pb2` messages, and a `FakeRpcError(grpc.RpcError)` that
carries just what `grpc_calls.call()` inspects (`.code()`, `.details()`,
`.trailing_metadata()`). Tests override the `get_stub` dependency via
`app.dependency_overrides`. No network, no real gRPC server, no live Data
Service anywhere in this test suite.

## Local Python environment note (for the orchestrator)

This service's dev/test work used two **local, isolated virtualenvs**, never
the bare global `python` on PATH:

- Initially, a scratchpad venv (`.venv_worklist`, outside the repo) with
  `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `grpcio`,
  `protobuf`, `httpx`, `pytest`, `ruff` installed via `pip install
  --quiet <pkgs>` (not `-e .`, since the repo isn't a git repo / no
  editable install was attempted).
- After the orchestrator's environment-correction notice, all further test
  runs used the shared `ecares/.venv` venv instead (already had everything
  needed: fastapi 0.141.1, pydantic 2.13.5, grpcio 1.84.0, httpx, pytest).
  No new packages were installed into `ecares/.venv` by this agent.
- **No installs were ever run against the bare global/host `python`** by
  this agent — only read-only `import` checks (e.g. `python -c "import
  fastapi"`) were run against it, to see what was already available, before
  creating the scratchpad venv. `pip check` against the global interpreter
  should be unaffected by this service's work.

## Ruff: one deliberate exception

`grpc_calls.py`'s generic `call()` helper uses `TypeVar` + `Callable[..., T]`
instead of the PEP 695 `def call[T](...)` syntax ruff's `UP047` suggests.
PEP 695 generics require Python 3.12, but this repo's own recorded
assumption (root `CLAUDE.md` / orchestrator assumption #4) is that
pure-logic code should still run on the host's Python 3.10. `ruff check`
therefore reports exactly one `UP047` finding here, left as-is on purpose.
Every FastAPI dependency default (`Depends(...)`, `Query(...)`) uses the
`Annotated[...]` form specifically because bare `x: T = Depends(...)`
defaults triggered `B008` inconsistently in this repo's ruff config
(observed emitting the same call, same shape, in some route functions but
not others — not chased further since ruff's B008 exemption for
`Annotated[...]`-style dependencies is unambiguous and is also the
currently-recommended FastAPI style either way).
