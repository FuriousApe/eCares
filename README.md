# Lean care-gap worklist

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Run

From the repo root, with `PYTHONPATH` set to the current directory:

```bash
PYTHONPATH=. uvicorn app.main:app --reload --port 8000
```

(PowerShell: `$env:PYTHONPATH = "."; uvicorn app.main:app --reload --port 8000`)

Open http://localhost:8000

On first run the app creates `app.db`, loads the CSVs from `data/`,
seeds two demo users, and runs the care-gap engine once.

## Demo logins

- **Jordan (Front Desk)** — scheduler role, sees scheduling tasks only
- **Dr. Patel (Clinical)** — clinical role, sees scheduling + referral tasks

## Tests

```bash
PYTHONPATH=. pytest tests/test_recompute.py -q
```
