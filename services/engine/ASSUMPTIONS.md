# Engine — assumptions and interpretations

Anything here that constrains the Data Service or the sync/outbox side should
be folded into the root `CLAUDE.md` by the orchestrator; this file is the
engine's own record per that file's instructions.

## Kafka message shape (`patient.changed`)

The outbox relay's exact payload is another agent's code, built concurrently,
so `extract_patient_id()` in `main.py` is deliberately defensive and documents
its own fallback chain rather than assuming one fixed shape:

1. Try to UTF-8-decode `msg.value` and `json.loads` it.
   - If the result is a `dict` with a `"patient_id"` key, use that value.
   - If the result is a bare JSON string (e.g. the relay just published
     `"P0201"` as the value), use it directly.
2. Otherwise (value missing, not UTF-8, not valid JSON, or JSON but neither
   of the above shapes), fall back to `msg.key` decoded as UTF-8 — the plan
   says the topic is "keyed by `patient_id`", so the key is expected to
   always be the patient id as raw bytes.
3. Otherwise, fall back to decoding `msg.value` itself as a raw UTF-8 string
   (covers a relay that publishes the bare id as the value with no key).
4. If none of the above yields anything, raise — a message with neither a
   parseable value nor a key is not something retrying can fix, so it isn't
   worth a fake DLQ round-trip (nothing recognizable to send).

If the Data Service's outbox relay turns out to publish some other envelope
(e.g. `{"event": "patient.changed", "patient_id": ..., "occurred_at": ...}`),
step 1 already handles it as long as `patient_id` is a top-level key.

## Idempotency key

`sha256(f"{patient_id}:{snapshot_hash}").hexdigest()`, per CLAUDE.md decision
#7 and the proto's `SaveEvaluationResultRequest.idempotency_key` comment.
`snapshot_hash` comes from `GetPatientSnapshotResponse` as-is; the engine
never recomputes it.

## `next_eval_at` (top-level field on `SaveEvaluationResultRequest`)

The proto's comment on `NeedResult.next_check_candidate` says the Data
Service "folds in any active decline snooze itself, since only it knows
about existing tasks" — the engine has no visibility into tasks at all (it's
stateless per the plan's evaluator steps 1-4). So the engine's `next_eval_at`
is only ever a **candidate**: the earliest of every `next_check_candidate`
and `tier_recheck_at` it computed across all programs for this patient — the
earliest day *something in the fact pattern* could flip, ignoring snoozes
entirely. The Data Service is expected to take the smaller of this value and
whatever a live snooze implies. When nothing in the evaluation carries a
future trigger date at all (e.g. every program is `not_eligible`, or every
need is a referral/no-history case with no due date), `next_eval_at` is sent
as an empty string rather than a sentinel date, since neither the plan nor
the proto specifies one.

## Encounter `is_upcoming` vs. recomputing from dates

`GetPatientSnapshotResponse`'s `EncounterFact.is_upcoming` is already
"relative to AS_OF_DATE" per its proto comment. The evaluator's `Encounter`
dataclass carries an `is_upcoming` field for shape parity, but the evaluator
itself never reads it — it always derives past/upcoming from
`encounter_date` compared against the `as_of_date` parameter it was given
(via `dates.is_past`), inside `_evaluate_need`. This keeps the evaluator's
correctness independent of whatever `as_of_date` the Data Service used to
compute its own flag (in practice they should always agree, since both read
`settings.effective_as_of_date()`, but the evaluator doesn't need to trust
that).

## P0087 — the "180-day boundary" case, and what actually drives it

The plan calls out P0087 as the strict-inequality boundary case ("PCP gap of
exactly 180 days ... not overdue"). Working from the real CSV rows: P0087 has
**no diagnoses at all** and is 46 as of 2026-04-08, so it lands in the
wellness **`standard`** tier (PCP cadence 365), not `high_priority`
(cadence 180). It also has an **upcoming** PCP encounter (2026-04-13). Per
the plan's step 4 ("An upcoming visit means no task" — checked first, no
further conditions), the actual decision path for P0087 is the
upcoming-visit rule, not the gap/cadence comparison: `has_upcoming=True` wins
before the gap is ever computed.

The last **past** PCP visit (2025-10-10) does sit exactly 180 days before
2026-04-08 — that's the number the plan's narrative names — but with a
cadence of 365 for this patient's actual tier, 180 days isn't close to
overdue regardless of `>` vs `>=`. The observable outcome the plan asserts
("No PCP task") still holds; a unit test (`test_p0087_...` in
`test_named_patients.py`) documents both the real path (upcoming-visit rule)
and the coincidental 180-day gap in the history. The strict `>` boundary
itself (a gap of exactly `cadence_days` is *not* overdue) is verified
directly and generically in `test_evaluator.py::test_strict_overdue_boundary_generic`,
independent of which real patient does or doesn't happen to hit it.

## Tier/eligibility condition grammar

- `when: no_result` and `when: default` are YAML **scalars** (bare strings),
  not `{no_result: true}` / `{default: true}` dicts — that's how they appear
  in the actual seed files, and `program_loader._parse_condition` branches on
  the raw value before checking `isinstance(raw, dict)`.
- A `gte`/`lt` dict may carry either or both keys; a dict is only accepted as
  a `gte`/`lt` condition if it contains at least one of them, checked after
  `any`/`min_age`/`diagnosis_prefix` so those aren't misread as an
  (empty) numeric range.
- `diagnosis_prefix` values are matched with plain `str.startswith` against a
  tuple of prefixes, never a regex — `G47.3`'s literal dot is just a literal
  character in that comparison, exactly as the plan calls out.
- Eligibility (`min_age` / `any_diagnosis_prefix`) and a tier's `any:` list
  (`min_age` / `diagnosis_prefix`) use different key names for what's
  conceptually the same idea (`any_diagnosis_prefix` vs `diagnosis_prefix`)
  because that's what the two real YAML files actually use; the loader keeps
  them as two distinct, non-interchangeable keys rather than aliasing them,
  since inventing a shared name the YAML doesn't use would be exactly the
  kind of unrequested abstraction ponytail rules out.

## Program loading and `UpsertPrograms`/`ListPrograms`

Per CLAUDE.md decision #9: `program_loader.load_programs()` parses the YAML
into dataclasses; `main.py` converts those to `ProgramDefinition` proto
messages (`definition_json` = `json.dumps(program_to_dict(program))`, never
the raw YAML text) and calls `UpsertPrograms` once at startup, then calls
`ListPrograms` and parses `definition_json` back via `from_proto_program` for
the programs actually used to evaluate patients — so a program state that
only exists in the Data Service (e.g. a future admin deactivation) is what
the engine acts on, not just whatever's on local disk at boot.

## Host test environment

The host's global Python 3.10 had `protobuf==4.23.2` / no `aiokafka` /
no `pydantic-settings`, too old for the generated `libs/common/grpc_gen`
stubs (which need `protobuf>=5.28`'s `runtime_version` module) and missing
outright for `aiokafka`/`pydantic-settings`. `pip install -e .` at the repo
root refuses on this host (`requires-python = ">=3.12"`, host is 3.10, per
CLAUDE.md decision #4). A concurrent agent's `pip install` on the same
global site-packages was also observed flipping `protobuf` back down to
4.23.2 mid-session. Rather than keep fighting a shared global environment,
tests here run from a dedicated `.venv_engine/` (created with
`python -m venv`, pinned deps installed from `pyproject.toml`'s versions) —
see `README.md`. This venv is local, untracked, and specific to this
service; it doesn't touch `.venv_ds` or any other agent's environment.

## Retry / DLQ behavior

Three attempts (`settings.kafka_max_retries`) with a short linear backoff
(`0.5 * attempt` seconds) in-process before giving up on a message. On final
failure, the raw Kafka message (both `key` and `value`, unparsed) is
republished verbatim to `settings.kafka_topic_dlq`, then the original
offset is committed — so a single bad patient (bad data, a Data Service
outage limited to one call, whatever) can never block the rest of the
partition, and "at least once" is preserved because the offset is committed
only after either a successful save or a completed DLQ hand-off, never
before.
