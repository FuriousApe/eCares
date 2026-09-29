# services/ui

React (Vite + TypeScript) front end for the Worklist API, built for **front desk and call center staff**: quick to scan, one obvious next step per row, and everything needed for a phone call in one panel.

## What staff see

| Screen | Purpose |
|---|---|
| **Worklist** | Tasks grouped into *To do*, *My tasks*, *Overdue* and *All active*. Filter by visit type, program (and task type for clinical). Search loaded rows by name, phone or ID (`/` jumps to search). Each row has a single primary button: **Take task**, then **Booked ✓** / **Complete ✓**. |
| **Patient panel** (click any row) | Big tap-to-call phone number with Copy, language (highlighted when not English), primary doctor, programs, the patient's tasks with all actions, care schedule and per-task history. |
| **Patients** | Server-side search by name, phone or ID for inbound calls. |
| **Admin** (admin role only) | Load data, re-check due patients or everyone, recent data loads. |

Task actions use plain language: **Take task**, **Booked**, **Call back later** (returns the task to the shared list after a chosen date), **Patient declined** (with reason and how long not to ask again).

If two people act on the same task, the API rejects the stale one (409). The UI tells the user, refreshes, and never overwrites a colleague's work.

## Run locally

```sh
cd services/ui
npm install
npm run dev          # http://localhost:3000
```

Port 3000 is required: it is the origin the Worklist API's CORS setting allows. The API address comes from `public/config.js` (`http://localhost:8000` by default).

```sh
npm run build        # typecheck + production build into dist/
npm run typecheck
```

## Run with Docker Compose

`docker compose up ui` (or the whole stack). The Dockerfile builds the app with Node, then serves `dist/` with Python's stdlib `http.server` on port 3000 and templates `WORKLIST_API_BASE_URL` into `config.js` at container start. Unchanged from the previous UI, so `docker-compose.yml` needs no edits.

## Sign-in

The backend has no real auth (per the plan): it trusts `X-User-Role` and `X-User-Id`. The header dropdown picks a demo user, and the choice is remembered in the browser.

| User | Role | Sees |
|---|---|---|
| Jordan Lee | Front Desk (`scheduler`) | Scheduling tasks |
| Dr. Patel | Clinical (`clinical`) | Scheduling + referral tasks |
| Sam Rivera | Admin (`admin`) | Everything, plus the Admin page |

## Layout

```
src/
  api.ts            typed fetch client, ApiError (409 = someone else got there first)
  session.tsx       current user, API client, meta (as-of date)
  hooks.ts          usePaged (cursor pagination that never flashes empty), debounce, hash routing
  format.ts         dates, phone numbers, plain-language labels
  components/       TaskActions (+ modals), PatientPanel (drawer), Badge/Modal/Toasts
  pages/            Worklist, Patients, Admin
  styles.css        design tokens + all styles (no UI kit)
```

Dependencies are just `react` and `react-dom`. Routing is hash-based, so no server rewrite rules are needed.

See `ASSUMPTIONS.md` for decisions and known limits.
