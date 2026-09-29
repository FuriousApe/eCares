# services/ui: assumptions

Out of scope for the backend MVP plan; built at the user's request (see root `CLAUDE.md`, Repo layout). This replaces the earlier single-file static page with a React app.

## Users and design intent

- Users are **front desk and call center staff**: they work from a queue, on the phone, often interrupted. The design favors a short path (take, call, record), large click targets, plain words over system terms (`scheduling` shows as "Schedule visit", `in_progress` as "Yours" / "With <name>"), and no modal chains.
- Accessible by default: keyboard operable rows and dialogs, visible focus, `Esc` closes overlays, status is text as well as color, dialogs have `role="dialog"`. Not audited against WCAG.

## API contract

- Uses only the real Worklist API shapes from `services/worklist_api/schemas.py` (mirrored in `src/types.ts`). Nothing is guessed, unlike the old UI.
- Auth is the plan's: `X-User-Role` + `X-User-Id` headers from a demo-user dropdown. The three demo user ids (`sched1`, `clin1`, `admin1`) are free text to the API; "mine" means `assigned_to === X-User-Id`.
- The API does not check that the completer is the claimer, so any user with visibility can complete an in-progress task. The UI only offers Complete / Call back later / Declined to the claimer and shows "With <name>" for others. That is a UI convention, not enforcement.
- Stale writes: every mutation sends the task's `version`. A 409 shows a message and refetches.

## Behavior choices

- **Worklist views** are presets over API filters: To do = `status=open`; My tasks = `status=in_progress&assigned_to=<me>`; Overdue = `overdue=true`; All active = API default (open + in progress). Snoozed tasks are hidden by the API default (`include_snoozed=false`).
- **Worklist search is client-side over loaded rows** because `GET /tasks` has no `q`. It is labelled as such when more pages exist. Use the Patients page for full server-side search.
- **Completing** offers only resolutions that fit the task type: scheduling -> `booked`; referral -> `referral_approved` / `referral_not_indicated`. The API accepts any of the three for either type; this is a UX narrowing.
- **Call back later** uses `POST /tasks/{id}/snooze` (task returns to `open`, unassigned, hidden until the date). Quick dates are computed from the API's `as_of_date`, not the browser clock, because the demo data is dated 2026-04-08.
- **Patient declined** uses `POST /tasks/{id}/decline` with a reason and `snooze_days` (30/60/90/180, default 90).
- The specialty filter list is fixed (Cardiology, Endocrinology, Nephrology, Ophthalmology, PCP, Podiatry) because there is no endpoint listing specialties. A new specialty in a program needs a one-line edit in `pages/Worklist.tsx`.
- Snooze / decline reasons are fixed lists in `TaskActions.tsx`. The API stores the reason as free text.
- No auto-refresh or websockets. Lists refetch after any action and on the Refresh button.

## Build and serving

- Vite + React 19 + TypeScript, plain CSS, no component library or router package. Hash routing avoids server rewrite rules, so the stdlib `http.server` in the Dockerfile is enough.
- `public/config.js` is copied unhashed into `dist/`, and the Dockerfile templates `WORKLIST_API_BASE_URL` into it at container start (same mechanism as before).
- Dev server and preview are pinned to port 3000 because the API's CORS allow-list is `http://localhost:3000`. Serving from another origin needs the API's CORS setting changed.

## Known limits

- No unit or browser tests yet. It was verified by typechecking, a production build, and manual runs against a mock of the API for the worklist, patient panel, claim and complete flows. **It has not been run against the live Compose stack**, and the Docker image build has not been run.
- Admin page result rendering (`counts_json` summary) is generic because the shape of a sync run's counts is not fixed by the schema.
- No dark mode, no i18n, desktop-first layout (usable on a tablet; not tuned for phones).
