# Data Service — assumptions and notes

This is a resume of an interrupted build. Everything listed under "already
correct" below was written by the previous pass and verified, not rewritten,
by this one. See `CLAUDE.md` (repo root) for the cross-service decisions this
file assumes as given (`#1`-`#13`).

## CLAUDE.md #11 and #12 — verified against, both already matched

- **`next_eval_at` (#11):** `repositories/evaluation.save_evaluation_result`
  takes the engine's `next_eval_at_candidate` verbatim (empty string on the
  wire already decoded to `None` in `servicer.SaveEvaluationResult`) and folds
  in `snooze_until + 1 day` for any declined task at a key just evaluated that
  is still snoozed, via `evaluation_rules.compute_next_eval_at` (a plain
  `min()` over non-`None` candidates). Already correct; no change needed.
- **Idempotency key (#11):** compared verbatim
  (`state.last_idempotency_key == idempotency_key`) — never recomputed on this
  side. `hashing.idempotency_key()` exists only as a documented, unit-tested
  reference implementation of the engine's algorithm; nothing in the request
  path calls it. Already correct.
- **Kafka payload shape (#11):** every `write_outbox(...)` call across
  `repositories/tasks.py`, `repositories/evaluation.py` and
  `repositories/sync.py` writes `{"patient_id": ..., ...}` as the JSON
  payload, keyed by `patient_id`. Already correct.
- **gRPC error convention (#12):** `servicer._abort` sets both the trailing
  metadata (`("code", err.code)`) and the matching `grpc.StatusCode`
  (`not_found`->`NOT_FOUND`, `version_conflict`->`ABORTED`,
  `illegal_transition`->`FAILED_PRECONDITION`,
  `validation_error`->`INVALID_ARGUMENT`) for every `AppError` raised from
  every RPC that can fail. `FORBIDDEN`/`PERMISSION_DENIED` is mapped for
  completeness but never actually raised anywhere in this service — hidden-
  by-role always comes back as `NotFoundError` (verified by grep and by
  `tests/test_tasks_repo.py::test_scheduler_role_cannot_see_a_referral_task_gets_not_found_not_forbidden`).
  Already correct.

## What was actually broken, and fixed in this pass

1. **4 failing tests in `test_evaluation_repo.py`** — not a service bug. Each
   called `session.refresh(task)` right after `save_evaluation_result()`
   without an intervening `session.flush()`. SQLAlchemy's `Session.refresh()`
   expires the instance's attributes *before* it autoflushes, which discards
   an uncommitted in-memory change before it's ever written — the refreshed
   read then sees the pre-mutation row. In production this never bites
   because `db.session_scope()`'s `session.commit()` flushes before the
   caller ever reads the result again. Fixed by adding `session.flush()`
   before each `session.refresh(task)` in the affected tests. One of the four
   (`test_specialty_dropped_from_new_tier_closes_task_as_tier_changed`) had a
   second, real fixture gap: it asserted a task closes as `tier_changed` when
   its specialty drops out of a new tier, but never created the `needs` row
   that a real prior evaluation would have (the "stale need" diff in
   `save_evaluation_result` only fires for specialties the stored `needs`
   table still remembers) — added that row to the fixture.
2. **Redis caching for `ListTasks`/`ListPatients`/`ListPrograms` was entirely
   unwired.** `cache.py` had the full generation-counter scheme
   (`worklist_cache_key`, `cache_get_json`/`cache_set_json`,
   `get_active_programs`/`set_active_programs`) implemented and unit-testable,
   but nothing in `servicer.py` ever called it — every read hit MySQL
   directly regardless. Added a small `_cached_page()` wrapper used by both
   `ListPatients` and `ListTasks` (cache hit skips the repository call
   entirely; a miss runs it and caches the plain-dict result under
   `worklist:{generation}:{hash}` for `worklist_cache_ttl_seconds`), and wired
   `ListPrograms` to read/populate `programs:active`. Patient detail
   (`GetPatient`) is still never cached, per the plan. New tests:
   `tests/test_cache.py` (the Redis helpers, Redis calls mocked out) and
   `tests/test_servicer_cache.py` (`_cached_page` hit/miss behavior).
3. **`cache.get_client()` had no socket timeout.** The module's own docstring
   promises "if Redis is unreachable, reads still work" via the `_safe()`
   wrapper's `except redis.RedisError`, but `redis.Redis(...)` was constructed
   with no `socket_connect_timeout`/`socket_timeout`, so an unreachable Redis
   host would hang the calling RPC on the OS-level TCP/DNS timeout instead of
   raising a catchable `RedisError` quickly. Confirmed this by hand (a call
   against an unresolvable `redis` hostname hung past 15s). Added
   `socket_connect_timeout=1, socket_timeout=1`. This bounds the TCP-connect
   phase; a genuinely unresolvable hostname can still take a few seconds in
   DNS resolution itself (not something `redis-py`'s timeout parameter
   covers) — a non-issue in the real Docker Compose network where `redis`
   resolves immediately, and irrelevant to the test suite since no unit test
   exercises a live Redis connection.
4. **`uq_one_open_task` unique-index violations were not translated into a
   clean error.** Added a narrow `except IntegrityError` in
   `db.session_scope()` that raises `VersionConflictError` when the DB error
   names that constraint, and re-raises anything else unchanged. In practice
   the one code path that inserts a `Task` (`save_evaluation_result`) already
   avoids tripping this constraint under concurrency, because it takes a
   `SELECT ... FOR UPDATE` lock on the evaluated patient's
   `patient_eval_state` row for the whole diff+write, serializing every
   evaluation of that patient — so this is a safety net for the "surface a
   clean conflict, not a raw IntegrityError" requirement rather than a path
   that's actually reachable today. Covered by
   `tests/test_db_session_scope.py` using a fake session (no real MySQL
   needed to exercise the translation logic).

## Everything else read and verified correct, unchanged

- **Task state machine** (`task_state.py`): matches the plan's "MVP task
  states" table exactly (open->in_progress on claim, in_progress->
  {completed,declined,open} on complete/decline/snooze, {open,in_progress}->
  closed on the engine's close action). Illegal transitions raise
  `IllegalTransitionError`.
- **Optimistic locking**: every write RPC (`repositories/tasks.py`) loads the
  task with `SELECT ... FOR UPDATE` (skipped on SQLite in tests, since it
  isn't supported there and tests are single-threaded), checks `version`
  before mutating, and bumps it by exactly 1.
- **Sync staging/dedup/quarantine** (`resource_rules.py`,
  `repositories/sync.py`): `UpsertFacts` deep-validates and hashes each row,
  staging accepted rows keyed by `(run_id, resource_type, chunk_number)` with
  delete-then-insert semantics (a retried chunk is a no-op, not an append);
  rows that fail shape validation are quarantined immediately rather than
  staged. `CompleteSyncRun` dedups staged rows by natural key (keeping the
  earliest-written row per key — the P0231 case), diffs against the live
  tables by `row_hash`, and enforces the patients FK there (deferred from
  `UpsertFacts` since child-resource chunks can arrive before their patient's
  chunk within the same run) — quarantining any row whose `patient_id` isn't
  live yet. All covered by `tests/test_sync_repo.py`.
- **Outbox relay** (`outbox.py`): a dedicated OS thread running its own
  asyncio loop with `aiokafka.AIOKafkaProducer` — the smallest way to use an
  async-only Kafka client from an otherwise-synchronous gRPC server, without
  moving the whole server to asyncio. `SELECT ... FOR UPDATE SKIP LOCKED`
  batches of 20, 3 attempts then a `patient.changed.dlq` publish (marked
  "done" either way so a poison message can't jam the relay forever).
- **Audit rows**: written in the same session/transaction as every state
  change (`write_audit` is always called before the enclosing
  `session_scope()` commits), for both writes and the two read RPCs the plan
  names (`GetPatient` per-call, `ListTasks`/`ListPatients` recording filters +
  row count once per call, not per row).
- **Resolution-picking rule for closed tasks** (the one place the plan is
  genuinely ambiguous, per its own admission): `evaluation_rules.
  pick_close_resolution` — a referral task closes `visit_found` the moment
  its specialty gets any visit (upcoming or past); otherwise an upcoming
  visit wins over a tier change, which wins over the generic `not_eligible`
  catch-all. This project's resolution of that ambiguity, not a plan
  requirement; unit-tested in `tests/test_evaluation_rules.py`.

## Definition-of-done test coverage (all four already present before this pass)

- Stale version -> conflict:
  `test_tasks_repo.py::test_claim_with_stale_version_raises_version_conflict`
- Illegal transition -> rejected:
  `test_tasks_repo.py::test_claiming_an_already_in_progress_task_is_illegal`,
  `::test_completing_an_open_task_is_illegal`,
  `test_task_state.py::test_illegal_transitions_rejected` (parametrized)
- Idempotency key submitted twice -> exactly-once:
  `test_evaluation_repo.py::test_same_idempotency_key_applies_nothing_the_second_time`
- Declined+snoozed key -> no new task, then a new task once the snooze
  passes: `test_evaluation_repo.py::test_declined_and_still_snoozed_key_creates_no_task`
  and `::test_task_created_once_the_snooze_has_passed`

Added in this pass (previously zero coverage): `tests/test_cache.py`,
`tests/test_servicer_cache.py`, `tests/test_db_session_scope.py`.

## Local tooling

Per CLAUDE.md #4: every command in this pass ran through
`ecares/.venv/Scripts/python.exe`, never the bare global `python`. No new
dependency was needed — everything used was already in the venv.

## Known non-issues / deliberately left alone

- `db.maybe_for_update()` skips `FOR UPDATE` on SQLite (unsupported there);
  the concurrency guarantee it provides (serializing evaluations of one
  patient, and task mutations of one task) is real only against MySQL, and
  the plan's "20 parallel saves for one patient" check is a MySQL-level
  integration check, not something a SQLite unit test can exercise honestly
  — this was already correctly called out as out-of-scope-for-unit-tests in
  the existing test docstrings, and this pass agrees with that call.
- `ListTasksRequest.sort` is accepted but not wired to an alternate cursor
  shape (`pagination.py`'s own docstring already flags this as a deliberate
  ponytail cut — the plan's verification checks counts and role filters, not
  sort order). Left as-is.
