# Care gap engine — scaled build

Production-shaped version of the care-gap worklist (target: ~1M patients,
thousands of programs): React UI, Worklist API, gRPC Data Service, Kafka-driven
engine workers, MySQL and Redis. Design notes are in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and
[`docs/DATABASE.md`](docs/DATABASE.md).

## Live demo

https://ecares-abhinav-1745.azurewebsites.net

This is the **lean build on the `main` branch** (single FastAPI process +
SQLite), hosted on the Azure App Service free tier. It sleeps when idle, so the
first request can be slow. This scaled build is not hosted; run it locally as
below.

## Run locally

Requires Docker.

```bash
make demo        # build + start everything, then load the CSVs from data/
```

- Dashboard: http://localhost:3000
- Swagger UI: http://localhost:8000/docs

Without `make`: run the commands listed under `up` and `seed` in the
[`Makefile`](Makefile) (`docker compose up ...`).

Other targets: `make down` (stop and wipe volumes), `make logs`, `make test`,
`make verify`.
