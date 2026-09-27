# services/ui — assumptions

Out of scope for the backend MVP plan; built standalone per explicit request
(see root `CLAUDE.md` → Repo layout). Reads only the plan's "REST API for
Swagger" section — no other part of the plan applies here.

## API base URL

`config.js` sets `window.WORKLIST_API_BASE_URL`, defaulting to
`http://localhost:8000`. The Dockerfile's `CMD` runs `sed` on container
start to replace that default with the `$WORKLIST_API_BASE_URL` env var
docker-compose.yml already sets (also `http://localhost:8000` — the browser
talks to the API container's published port directly, not through the `ui`
container, so compose's default and the page's default happen to match).
The page also has an "API base" text field, seeded from `config.js` but
overridable and persisted to `localStorage`, so the templating step is a
convenience, not a hard requirement — if it fails for any reason the on-page
field is the fallback.

## Endpoint response shapes I guessed at

The plan's table gives request params and one example task object, but not
full response envelopes for every endpoint. Guesses, defended defensively in
JS (try several plausible key names, never throw on an unexpected shape):

- `GET /tasks`, `GET /patients`: assumed `{tasks: [...], next_cursor}` /
  `{patients: [...], next_cursor}` (falls back to `items`/`results`, or a
  bare array).
- `GET /tasks/{id}`: assumed either the flat task shape from the plan's
  example, or `{task: {...}, history: [...]}` — code unwraps `.task` if
  present.
- `POST /tasks/{id}/claim|complete|decline|snooze`: assumed each returns the
  updated task in the same shape as the `GET /tasks` list item (same
  unwrap-`.task`-if-present handling).
- `GET /meta`: assumed keys close to `as_of_date`, `last_sync_at`,
  `task_counts` (an object of counts) — tries a couple of common variants
  and falls back to whatever is there without erroring.
- `GET /patients/{id}`: assumed `{patient_id, first_name, last_name,
  enrollments: [{program_id, tier}], needs: [{specialty, last_visit,
  due_date, upcoming}], tasks: [...]}`.
- `GET /admin/sync-runs`: shape fully unknown — rendered generically as a
  table from `Object.keys()` of the first row, so it degrades gracefully
  whatever the real columns are.
- `POST /admin/sync`, `POST /admin/evaluate`: response just JSON-dumped to
  the screen rather than parsed into specific fields.

If the real API differs, only the small render/unwrap helpers in
`index.html` need touching — the fetch/header/error/pagination plumbing is
shape-agnostic.

## Filter params

Cross-checked against the plan's table, which is authoritative:
`GET /tasks` → `specialty, task_type, status, program, tier, overdue` (the
UI skips `assigned_to`, `include_snoozed`, `sort` — not asked for, and
`status` left blank sends no param so the API's own default, open + in
progress, applies). `GET /patients` → `q, specialty, task_type, status`
(the plan's table also lists `program`/`tier` here, but the task brief
explicitly scoped the patients view to "the same specialty/task_type/status
filters" plus `q`, so those two were left out to match the brief).

## Other

- No build step, no framework, one HTML file + one two-line config file.
  Styling is plain CSS, no design system pulled in for a demo dashboard.
- `Dockerfile` uses `python:3.12-slim` + stdlib `http.server`, not nginx —
  static files with zero routing/caching needs don't justify a second web
  server to configure and keep patched.
- Row actions use `prompt()`/`alert()` for the small set of inputs they need
  (resolution, note, reason, snooze_days, until) rather than building modal
  dialog markup — acceptable for an internal ops demo, not for a real
  product.
- 409 handling re-fetches only the affected row (`GET /tasks/{id}`) and
  patches every matching `<tr>` in both the worklist and patient-detail
  tables, rather than re-fetching whole pages — keeps "Load more" state and
  scroll position intact.
- Auth is exactly what the plan specifies: no login UI, just a role
  dropdown and a free-text user id that become `X-User-Role`/`X-User-Id` on
  every request.
