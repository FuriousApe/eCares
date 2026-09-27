# Engine

Consumes `patient.changed` off Kafka, evaluates a patient against the active
programs, and saves the result through the Data Service. No MySQL access —
everything goes through gRPC.

- `evaluator.py` — the pure rules engine (no I/O). Given a patient snapshot,
  parsed program definitions and an as-of date, decides eligibility, tier,
  and a `no_task` / `scheduling` / `referral` decision per need.
- `program_loader.py` — parses `seeds/programs/*.yaml` into the dataclasses
  `evaluator.py` expects, and converts to/from the `ProgramDefinition` proto
  message for `UpsertPrograms` / `ListPrograms`.
- `main.py` — the `ROLE=engine` entrypoint: loads and upserts programs, reads
  them back via `ListPrograms`, then runs the `aiokafka` consumer loop.

See `ASSUMPTIONS.md` for the exact Kafka message shape assumed, the
`next_eval_at` semantics, and a few condition-grammar and boundary-case notes.

## Running the tests

Pure-logic tests, no Data Service, no Kafka, no MySQL needed — they read
`seeds/programs/*.yaml` and `ecares/data/*.csv` directly:

```
python -m pytest services/engine/tests -v
```

Requires `pyyaml` and the generated `libs/common/grpc_gen` stubs to be
importable (needs `protobuf>=5.28`, since the generated code uses the
`runtime_version` module added in that release — an older `protobuf` on the
host will fail to import `program_loader.py` / `main.py`, though `evaluator.py`
alone has no such dependency and imports with any version).

The host's system Python (3.10) didn't have current-enough `protobuf`, or
`aiokafka`/`pydantic-settings` at all, and `pip install -e .` refuses there
(`pyproject.toml` requires `>=3.12`). If you hit the same thing, set up a
throwaway venv with the versions `pyproject.toml` pins and run the tests from
it (this doesn't need Docker or Compose — the whole test suite is pure
Python + stdlib `csv`/`yaml` parsing):

```
python -m venv .venv_engine
.venv_engine\Scripts\python.exe -m pip install pyyaml "protobuf>=5.28" "grpcio>=1.66" \
    "aiokafka>=0.11" "pydantic>=2.9" "pydantic-settings>=2.6" "pytest>=8.3" "pytest-asyncio>=0.24"
.venv_engine\Scripts\python.exe -m pytest services/engine/tests -v
```

What's covered:

- `test_evaluator.py` — tier boundary math (`gte`/`lt` combos, `no_result`,
  `default`, `any`), the strict overdue boundary generically, eligibility,
  and needs/task decisions, all against small synthetic programs/patients.
- `test_program_loader.py` — parses both real seed YAML files and checks the
  round trip through JSON (and through a `ProgramDefinition` proto message)
  loses nothing.
- `test_named_patients.py` — the plan's verification patients (P0201, P0002,
  P0087, P0231, P0029, P0003, P0018, P0004), evaluated with the real parsed
  YAML against rows read directly from `ecares/data/*.csv` with stdlib `csv`.
