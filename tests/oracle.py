"""Independent verification oracle.

Computes the expected Care Gap Engine result STRAIGHT FROM THE CSVs, in
pandas, re-deriving the eligibility / tier / needs rules from the plan's
"Rules and task generation" section from scratch. This module must NEVER
import `services.engine` (or any other project rules code) -- see
`CLAUDE.md` decision #8. If it did, it would stop being an independent
oracle and become a tautology (the evaluator "agreeing with itself").

Run standalone::

    ecares/.venv/Scripts/python.exe tests/oracle.py
    ecares/.venv/Scripts/python.exe tests/oracle.py --as-of 2026-05-08 --json

At the default as-of date (2026-04-08) this asserts every number in the
plan's Verification section and the named-patient edge cases, and exits
non-zero with a clear diff on any mismatch -- this is what `make verify`
runs. At any other as-of date there is no fixed expected table to check
against (the plan only worked one out for 2026-04-08), so the script just
prints the computed numbers; `tests/integration/test_time_travel.py` uses
that mode (via `--as-of`) to get a fresh oracle at a different date and
diffs it against what the live system produced after re-evaluating.
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

DEFAULT_AS_OF = date(2026, 4, 8)
DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# --- program definitions, re-derived independently from the plan's YAML text
# (never read from seeds/programs/*.yaml, and never from evaluator code) ---

DIABETES_ELIGIBILITY_PREFIXES = ("E10", "E11")

# (tier_name, predicate over the in-window HbA1c value or None, needs dict)
DIABETES_TIERS: list[tuple[str, object, dict[str, int]]] = [
    (
        "high_risk",
        lambda v: v is not None and v >= 9.0,
        {
            "Endocrinology": 90,
            "Cardiology": 90,
            "Podiatry": 180,
            "Ophthalmology": 365,
            "Nephrology": 180,
        },
    ),
    (
        "moderate",
        lambda v: v is not None and 7.0 <= v < 9.0,
        {"Endocrinology": 180, "Ophthalmology": 365, "Podiatry": 365},
    ),
    ("low_risk", lambda v: v is not None and v < 7.0, {"Endocrinology": 365, "Ophthalmology": 365}),
    ("unmonitored", lambda v: v is None, {"Endocrinology": 90}),
]

WELLNESS_HIGH_PRIORITY_DIAG_PREFIXES = (
    "E10",
    "E11",
    "I10",
    "E78",
    "J45",
    "N18",
    "I25",
    "E03",
    "G47.3",
    "M81",
)
PRIMARY_CARE_SPECIALTY = "PCP"


def months_before(d: date, months: int) -> date:
    """`d` minus `months` calendar months, clamping to the shorter month.

    Written independently of `libs.common.dates.months_before` (same idea,
    separate implementation) so the oracle owns its own date arithmetic.
    """
    month_index = d.month - 1 - months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def age_at(dob: date, as_of: date) -> int:
    return as_of.year - dob.year - ((as_of.month, as_of.day) < (dob.month, dob.day))


# ============================================================================
# Data loading
# ============================================================================


@dataclass
class Frames:
    patients: pd.DataFrame
    diagnoses: pd.DataFrame
    labs: pd.DataFrame
    encounters: pd.DataFrame
    encounters_raw: pd.DataFrame  # before natural-key dedup, for the P0231 check


def load_frames(data_dir: Path) -> Frames:
    patients = pd.read_csv(data_dir / "patients.csv", dtype=str)
    diagnoses = pd.read_csv(data_dir / "diagnoses.csv", dtype=str)
    labs = pd.read_csv(data_dir / "labs.csv", dtype=str)
    encounters_raw = pd.read_csv(data_dir / "encounters.csv", dtype=str)

    patients["date_of_birth"] = pd.to_datetime(patients["date_of_birth"]).dt.date
    diagnoses["diagnosed_date"] = pd.to_datetime(diagnoses["diagnosed_date"]).dt.date
    labs["result_date"] = pd.to_datetime(labs["result_date"]).dt.date
    labs["result_value"] = labs["result_value"].astype(float)
    encounters_raw["encounter_date"] = pd.to_datetime(encounters_raw["encounter_date"]).dt.date

    # Data Service dedup: unique on (patient_id, specialty, encounter_date,
    # provider_name) -- drops the one P0231 duplicate row.
    encounters = encounters_raw.drop_duplicates(
        subset=["patient_id", "specialty", "encounter_date", "provider_name"], keep="first"
    ).reset_index(drop=True)

    return Frames(patients, diagnoses, labs, encounters, encounters_raw)


# ============================================================================
# Per-patient evaluation
# ============================================================================


@dataclass
class NeedDecision:
    specialty: str
    cadence_days: int
    last_visit_date: date | None
    has_upcoming: bool
    decision: str  # no_task | scheduling | referral


@dataclass
class ProgramOutcome:
    program_id: str
    eligible: bool
    tier: str | None = None
    needs: list[NeedDecision] = field(default_factory=list)


def _diagnosed_prefixes(diag_codes: list[str], prefixes: tuple[str, ...]) -> bool:
    return any(code.startswith(prefixes) for code in diag_codes)


def _decide_need(
    encounters_pt: pd.DataFrame, specialty: str, cadence_days: int, as_of: date
) -> NeedDecision:
    rows = encounters_pt[encounters_pt["specialty"] == specialty]
    past = rows[rows["encounter_date"] <= as_of]
    upcoming = rows[rows["encounter_date"] > as_of]
    has_upcoming = len(upcoming) > 0
    last_visit_date = past["encounter_date"].max() if len(past) else None

    if has_upcoming:
        decision = "no_task"
    elif last_visit_date is None:
        # No history at all: a referral task for a specialist, nothing for PCP.
        decision = "no_task" if specialty == PRIMARY_CARE_SPECIALTY else "referral"
    else:
        gap_days = (as_of - last_visit_date).days
        decision = "scheduling" if gap_days > cadence_days else "no_task"

    return NeedDecision(specialty, cadence_days, last_visit_date, has_upcoming, decision)


def evaluate_diabetes(
    patient_id: str,
    diag_codes: list[str],
    labs_pt: pd.DataFrame,
    encounters_pt: pd.DataFrame,
    as_of: date,
) -> ProgramOutcome:
    if not _diagnosed_prefixes(diag_codes, DIABETES_ELIGIBILITY_PREFIXES):
        return ProgramOutcome("diabetes_management", eligible=False)

    window_start = months_before(as_of, 6)
    a1c = labs_pt[
        (labs_pt["test_name"] == "HbA1c")
        & (labs_pt["result_date"] <= as_of)
        & (labs_pt["result_date"] >= window_start)
    ]
    value = None
    if len(a1c):
        latest = a1c.loc[a1c["result_date"].idxmax()]
        value = float(latest["result_value"])

    tier_name, needs_def = None, None
    for name, predicate, needs in DIABETES_TIERS:
        if predicate(value):
            tier_name, needs_def = name, needs
            break
    assert tier_name is not None  # the tier list is exhaustive (last arm is `no_result`)

    needs = [
        _decide_need(encounters_pt, specialty, cadence, as_of)
        for specialty, cadence in needs_def.items()
    ]
    return ProgramOutcome("diabetes_management", eligible=True, tier=tier_name, needs=needs)


def evaluate_wellness(
    patient_id: str,
    dob: date,
    diag_codes: list[str],
    encounters_pt: pd.DataFrame,
    as_of: date,
) -> ProgramOutcome:
    age = age_at(dob, as_of)
    if age < 18:
        return ProgramOutcome("primary_care_wellness", eligible=False)

    if age >= 65 or _diagnosed_prefixes(diag_codes, WELLNESS_HIGH_PRIORITY_DIAG_PREFIXES):
        tier_name, cadence = "high_priority", 180
    else:
        tier_name, cadence = "standard", 365

    need = _decide_need(encounters_pt, PRIMARY_CARE_SPECIALTY, cadence, as_of)
    return ProgramOutcome("primary_care_wellness", eligible=True, tier=tier_name, needs=[need])


# ============================================================================
# Aggregate computation
# ============================================================================


@dataclass
class ExpectedResult:
    as_of: date
    wellness_total: int
    wellness_high_priority: int
    wellness_standard: int
    diabetes_total: int
    diabetes_high_risk: int
    diabetes_moderate: int
    diabetes_low_risk: int
    diabetes_unmonitored: int
    tasks_total: int
    tasks_scheduling: int
    tasks_referral: int
    patients_with_task: int
    by_specialty: dict[str, dict[str, int]]
    outcomes_by_patient: dict[str, dict[str, ProgramOutcome]]
    p0231_dedup_count: int

    def to_json_dict(self) -> dict:
        d = {
            "as_of": self.as_of.isoformat(),
            "wellness_total": self.wellness_total,
            "wellness_high_priority": self.wellness_high_priority,
            "wellness_standard": self.wellness_standard,
            "diabetes_total": self.diabetes_total,
            "diabetes_high_risk": self.diabetes_high_risk,
            "diabetes_moderate": self.diabetes_moderate,
            "diabetes_low_risk": self.diabetes_low_risk,
            "diabetes_unmonitored": self.diabetes_unmonitored,
            "tasks_total": self.tasks_total,
            "tasks_scheduling": self.tasks_scheduling,
            "tasks_referral": self.tasks_referral,
            "patients_with_task": self.patients_with_task,
            "by_specialty": self.by_specialty,
            "p0231_dedup_count": self.p0231_dedup_count,
        }
        return d


def compute_expected(as_of: date, data_dir: Path = DEFAULT_DATA_DIR) -> ExpectedResult:
    frames = load_frames(data_dir)

    diagnoses_past = frames.diagnoses[frames.diagnoses["diagnosed_date"] <= as_of]
    diag_by_patient = diagnoses_past.groupby("patient_id")["icd_code"].apply(list).to_dict()
    labs_by_patient = {pid: g for pid, g in frames.labs.groupby("patient_id")}
    enc_by_patient = {pid: g for pid, g in frames.encounters.groupby("patient_id")}
    empty_enc = frames.encounters.iloc[0:0]
    empty_labs = frames.labs.iloc[0:0]

    outcomes_by_patient: dict[str, dict[str, ProgramOutcome]] = {}
    for _, prow in frames.patients.iterrows():
        pid = prow["patient_id"]
        dob = prow["date_of_birth"]
        codes = diag_by_patient.get(pid, [])
        enc = enc_by_patient.get(pid, empty_enc)
        labs_pt = labs_by_patient.get(pid, empty_labs)

        wellness = evaluate_wellness(pid, dob, codes, enc, as_of)
        diabetes = evaluate_diabetes(pid, codes, labs_pt, enc, as_of)
        outcomes_by_patient[pid] = {
            "primary_care_wellness": wellness,
            "diabetes_management": diabetes,
        }

    wellness_outcomes = [o["primary_care_wellness"] for o in outcomes_by_patient.values()]
    diabetes_outcomes = [o["diabetes_management"] for o in outcomes_by_patient.values()]

    wellness_total = sum(1 for o in wellness_outcomes if o.eligible)
    wellness_hp = sum(1 for o in wellness_outcomes if o.tier == "high_priority")
    wellness_std = sum(1 for o in wellness_outcomes if o.tier == "standard")

    diabetes_total = sum(1 for o in diabetes_outcomes if o.eligible)
    diabetes_counts = {t: 0 for t, _, _ in DIABETES_TIERS}
    for o in diabetes_outcomes:
        if o.eligible:
            diabetes_counts[o.tier] += 1

    by_specialty: dict[str, dict[str, int]] = {}
    tasks_scheduling = 0
    tasks_referral = 0
    patients_with_task: set[str] = set()

    for pid, outcomes in outcomes_by_patient.items():
        for outcome in outcomes.values():
            for need in outcome.needs:
                if need.decision == "no_task":
                    continue
                bucket = by_specialty.setdefault(need.specialty, {"scheduling": 0, "referral": 0})
                bucket[need.decision] += 1
                patients_with_task.add(pid)
                if need.decision == "scheduling":
                    tasks_scheduling += 1
                else:
                    tasks_referral += 1

    p0231_dedup_count = int(
        (
            (frames.encounters["patient_id"] == "P0231")
            & (frames.encounters["encounter_date"] == date(2024, 10, 2))
        ).sum()
    )

    return ExpectedResult(
        as_of=as_of,
        wellness_total=wellness_total,
        wellness_high_priority=wellness_hp,
        wellness_standard=wellness_std,
        diabetes_total=diabetes_total,
        diabetes_high_risk=diabetes_counts["high_risk"],
        diabetes_moderate=diabetes_counts["moderate"],
        diabetes_low_risk=diabetes_counts["low_risk"],
        diabetes_unmonitored=diabetes_counts["unmonitored"],
        tasks_total=tasks_scheduling + tasks_referral,
        tasks_scheduling=tasks_scheduling,
        tasks_referral=tasks_referral,
        patients_with_task=len(patients_with_task),
        by_specialty=by_specialty,
        outcomes_by_patient=outcomes_by_patient,
        p0231_dedup_count=p0231_dedup_count,
    )


# ============================================================================
# Fixed expected table (2026-04-08 only) -- the plan's Verification section
# ============================================================================

EXPECTED_SPECIALTY_BREAKDOWN = {
    "PCP": {"scheduling": 80, "referral": 0},
    "Endocrinology": {"scheduling": 30, "referral": 39},
    "Cardiology": {"scheduling": 8, "referral": 7},
    "Podiatry": {"scheduling": 16, "referral": 21},
    "Nephrology": {"scheduling": 7, "referral": 9},
    "Ophthalmology": {"scheduling": 13, "referral": 43},
}


def _check(failures: list[str], label: str, actual, expected) -> None:
    if actual != expected:
        failures.append(f"{label}: expected {expected!r}, got {actual!r}")


def check_fixed_numbers(result: ExpectedResult) -> list[str]:
    failures: list[str] = []
    _check(failures, "wellness_total", result.wellness_total, 288)
    _check(failures, "wellness_high_priority", result.wellness_high_priority, 217)
    _check(failures, "wellness_standard", result.wellness_standard, 71)
    _check(failures, "diabetes_total", result.diabetes_total, 115)
    _check(failures, "diabetes_high_risk", result.diabetes_high_risk, 29)
    _check(failures, "diabetes_moderate", result.diabetes_moderate, 39)
    _check(failures, "diabetes_low_risk", result.diabetes_low_risk, 24)
    _check(failures, "diabetes_unmonitored", result.diabetes_unmonitored, 23)
    _check(failures, "tasks_total", result.tasks_total, 273)
    _check(failures, "tasks_scheduling", result.tasks_scheduling, 154)
    _check(failures, "tasks_referral", result.tasks_referral, 119)
    _check(failures, "patients_with_task", result.patients_with_task, 151)

    for specialty, expected in EXPECTED_SPECIALTY_BREAKDOWN.items():
        actual = result.by_specialty.get(specialty, {"scheduling": 0, "referral": 0})
        _check(
            failures, f"{specialty}.scheduling", actual.get("scheduling", 0), expected["scheduling"]
        )
        _check(failures, f"{specialty}.referral", actual.get("referral", 0), expected["referral"])

    _check(failures, "P0231 stored encounters for 2024-10-02", result.p0231_dedup_count, 1)

    named = result.outcomes_by_patient

    p0201 = named["P0201"]["diabetes_management"]
    _check(failures, "P0201 tier", p0201.tier, "high_risk")
    p0201_needs = {n.specialty: n.decision for n in p0201.needs}
    _check(
        failures,
        "P0201 needs",
        p0201_needs,
        {
            "Endocrinology": "referral",
            "Podiatry": "referral",
            "Cardiology": "scheduling",
            "Ophthalmology": "scheduling",
            "Nephrology": "scheduling",
        },
    )

    p0002 = named["P0002"]["diabetes_management"]
    p0002_needs = {n.specialty: n.decision for n in p0002.needs}
    _check(failures, "P0002 Cardiology", p0002_needs.get("Cardiology"), "no_task")
    _check(failures, "P0002 Ophthalmology", p0002_needs.get("Ophthalmology"), "no_task")

    p0087 = named["P0087"]["primary_care_wellness"]
    p0087_pcp = next((n for n in p0087.needs if n.specialty == "PCP"), None)
    _check(failures, "P0087 PCP decision", p0087_pcp.decision if p0087_pcp else None, "no_task")

    p0029 = named["P0029"]["primary_care_wellness"]
    _check(failures, "P0029 wellness eligible", p0029.eligible, False)

    p0003 = named["P0003"]["primary_care_wellness"]
    p0003_pcp = next((n for n in p0003.needs if n.specialty == "PCP"), None)
    _check(failures, "P0003 PCP decision", p0003_pcp.decision if p0003_pcp else None, "no_task")
    _check(
        failures,
        "P0003 PCP last_visit_date (no past visit)",
        p0003_pcp.last_visit_date if p0003_pcp else "MISSING",
        None,
    )

    p0018 = named["P0018"]["primary_care_wellness"]
    p0018_pcp = next((n for n in p0018.needs if n.specialty == "PCP"), None)
    _check(
        failures,
        "P0018 has PCP visit history",
        p0018_pcp.last_visit_date is not None if p0018_pcp else False,
        True,
    )

    p0004 = named["P0004"]["diabetes_management"]
    _check(failures, "P0004 tier", p0004.tier, "unmonitored")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=DEFAULT_AS_OF.isoformat())
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--json", action="store_true", help="print the computed numbers as JSON")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of)
    result = compute_expected(as_of, Path(args.data_dir))

    if args.json:
        print(json.dumps(result.to_json_dict(), indent=2))

    if as_of != DEFAULT_AS_OF:
        if not args.json:
            print(
                f"as-of {as_of} has no fixed expected table (only {DEFAULT_AS_OF} does); "
                f"printing computed numbers only."
            )
            print(json.dumps(result.to_json_dict(), indent=2))
        return 0

    failures = check_fixed_numbers(result)
    if failures:
        print(f"ORACLE MISMATCH at as-of {as_of} ({len(failures)} failure(s)):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    if not args.json:
        print(
            f"Oracle OK at as-of {as_of}: every fixed number and named-patient check "
            "from the plan's Verification section matches."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
