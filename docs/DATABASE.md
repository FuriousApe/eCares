# Database Schema — MySQL 8 (`feature/scaled`)

Visual ER diagram: [`database-schema.drawio`](database-schema.drawio).
Source of truth: `services/data_service/models.py` and
`migrations/versions/0001_initial_schema.py`. Only the Data Service reads or
writes these tables.

Fourteen tables in three groups.

## Clinical facts (synced from source systems)

| Table | Key | Purpose |
|---|---|---|
| `patients` | PK `patient_id` | Demographics and PCP. `row_hash` drives change detection. |
| `diagnoses` | PK `id`; unique `(patient_id, icd_code, diagnosed_date)` | ICD codes per patient. Index on `patient_id`. |
| `labs` | PK `id`; unique `(patient_id, test_name, result_date)` | Lab results (for example HbA1c). Index on `patient_id`. |
| `encounters` | PK `id`; unique `(patient_id, specialty, encounter_date, provider_name)` | Past and upcoming visits. Index `(patient_id, specialty, encounter_date)` serves the "last visit" lookup. |

Each fact row carries a `row_hash` (sha256 of canonical values) so a sync only
writes rows that really changed. The unique natural keys make upserts
idempotent.

## Engine state and worklist

| Table | Key | Purpose |
|---|---|---|
| `programs` | PK `(program_id, version)` | Versioned program definition as JSON; `active` flag. Programs are data, so changing one needs no deploy. |
| `enrollments` | PK `(patient_id, program_id)` | Current tier per patient and program, with the `program_version` and `evaluated_at` that produced it. |
| `needs` | PK `(patient_id, program_id, specialty)` | Derived cadence, last visit, due date and `has_upcoming` for each required specialty. |
| `tasks` | PK `task_id` | The worklist. See below. |
| `patient_eval_state` | PK `patient_id` | Per-patient scheduler state: `next_eval_at`, `last_evaluated_at`, `last_idempotency_key`. Index `ix_eval_state_next_eval_at` makes "who is due?" cheap. |

### `tasks` in detail

| Column | Notes |
|---|---|
| `task_type` | enum `scheduling` / `referral` — drives role visibility. |
| `status` | enum `open`, `in_progress`, `completed`, `declined`, `closed`. |
| `resolution` | `booked`, `referral_approved`, `referral_not_indicated`, `visit_found`, `upcoming_visit`, `tier_changed`, `not_eligible`. |
| `due_date`, `snooze_until` | Target date; snooze expiry after a decline. |
| `assigned_to` | Claimant. |
| `program_version` | Program version that created the task. |
| `version` | **Optimistic lock.** Incremented on every mutation; stale writes are rejected (HTTP 409). |
| `open_key` | **Generated, persisted** = `patient|program|specialty` while status is `open` / `in_progress`, else `NULL`. `UNIQUE` (`uq_one_open_task`) means MySQL itself refuses a second live task for the same gap. `NULL`s do not collide, so closed history is unrestricted. |

Indexes: `ix_worklist (status, task_type, specialty, due_date)` for the
role-filtered, paginated worklist query; `ix_task_patient (patient_id)`.

## Platform: sync, events, audit

| Table | Key | Purpose |
|---|---|---|
| `sync_runs` | PK `run_id` | Ledger of each ingest run: status, timing, counts and watermarks (JSON). |
| `sync_quarantine` | PK `id`, FK `run_id → sync_runs` | Rows the Data Service rejected, with the raw row and reason. Index on `run_id`. |
| `staging_rows` | PK `id` | Transient landing area for chunks, keyed `(run_id, resource_type, chunk_number)`; one generic table for all four resources, with the row as JSON. Diffed against the live tables at `CompleteSyncRun`. |
| `outbox` | PK `id`; unique `event_id` | Transactional outbox. Rows are published to Kafka by the relay; `published_at` and `attempts` track delivery. Index `(published_at, id)` finds the next unpublished rows in order. |
| `audit_events` | PK `id`; unique `event_id` | Append-only history: actor, action, entity, before/after JSON, `request_id`, result. Indexed by `patient_id` and `entity`. |

## Relationships

- `patients` is the hub. `diagnoses`, `labs`, `encounters`, `enrollments`,
  `needs`, `tasks` and `patient_eval_state` all have a foreign key to
  `patients.patient_id`.
- `sync_quarantine.run_id → sync_runs.run_id`.
- **Deliberately not foreign keys:** `program_id` on `enrollments` / `needs` /
  `tasks` (programs are versioned, keyed by `(program_id, version)`), and
  `run_id` on `staging_rows` (transient rows). `audit_events.patient_id` is
  also unconstrained so history survives any cleanup.

## Design notes

- **Integrity in the database, not just code.** The `open_key` unique index and
  the natural-key unique constraints hold even if application code is wrong or
  two writers race.
- **Change detection by hash** avoids rewriting unchanged rows and lets
  `CompleteSyncRun` report exactly which patients need re-evaluation.
- **Hot-path indexing** targets three queries: the worklist page, "latest
  visit for this patient and specialty", and "patients due for re-check".
- **Growth.** `staging_rows` is prunable after a run completes. `outbox`
  (published rows) and `audit_events` are the append-heavy tables to archive or
  partition by date first.
