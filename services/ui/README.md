# services/ui

A minimal static dashboard for the Worklist REST API: role switcher, task
worklist with claim/complete/decline/snooze actions, a patient search/detail
view, and an admin panel (sync, evaluate, sync-run history). Plain HTML/CSS
and vanilla JS calling the API directly with `fetch` from the browser — no
build step, no framework, no npm install. See `ASSUMPTIONS.md` for the
endpoint-shape guesses and filter-param choices this made.

This is a demo dashboard against an MVP backend, not a product — see
`ASSUMPTIONS.md` for what was deliberately kept simple.

## Run standalone (no Docker)

```sh
cd services/ui
python -m http.server 3000
```

Open `http://localhost:3000`, set the "API base" field (top of the page) to
wherever the Worklist API is running, pick a role and a user id.

Or just open `index.html` directly in a browser (`file://`) — it still
works, since it's a static page with no server-side dependency.

## Run via Docker Compose

The root `docker-compose.yml` already builds this service:

```yaml
ui:
  build: ./services/ui
  environment:
    WORKLIST_API_BASE_URL: http://localhost:8000
  ports: ["3000:3000"]
  depends_on:
    - worklist-api
```

`docker compose up ui` (or `docker compose up` for the whole stack) serves
the page at `http://localhost:3000`. The container's `WORKLIST_API_BASE_URL`
is templated into `config.js` at container start; because the browser talks
to the Worklist API's published port on `localhost:8000` directly (not
through the `ui` container's network), the compose default already matches
what the page needs for local use — no extra config required.

## Files

- `index.html` — the entire app: markup, CSS and JS in one file.
- `config.js` — one line setting the default API base URL; templated by the
  Dockerfile's `CMD` from `$WORKLIST_API_BASE_URL` at container start.
- `Dockerfile` — `python:3.12-slim` serving the two files above with the
  stdlib `http.server` on port 3000.
