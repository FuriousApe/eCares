"""The pure rules engine core: no DB, no HTTP, no settings lookups beyond
what's passed in. Takes a patient snapshot, a list of parsed program
definitions and an as-of date; returns one `ProgramResult` per program.

Ported near-verbatim from the `main` branch's `services/engine/evaluator.py`
-- the declarative condition-tree design already satisfies "add a new
program without touching code," so there was nothing to redesign, only to
run in-process instead of behind gRPC. See ARCHITECTURE.md for why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.engine.dates import add_days, is_past, months_before

# ============================================================================
# Snapshot inputs
# ============================================================================


@dataclass(frozen=True)
class Diagnosis:
    icd_code: str
    diagnosed_date: date


@dataclass(frozen=True)
class LabResult:
    test_name: str
    result_value: float
    result_date: date


@dataclass(frozen=True)
class Encounter:
    specialty: str
    encounter_date: date


@dataclass(frozen=True)
class PatientSnapshot:
    patient_id: str
    age: int
    diagnoses: list[Diagnosis] = field(default_factory=list)
    labs: list[LabResult] = field(default_factory=list)
    encounters: list[Encounter] = field(default_factory=list)


def age_as_of(date_of_birth: date, as_of_date: date) -> int:
    years = as_of_date.year - date_of_birth.year
    had_birthday = (as_of_date.month, as_of_date.day) >= (date_of_birth.month, date_of_birth.day)
    return years if had_birthday else years - 1


# ============================================================================
# Program definition inputs (mirror the YAML schema)
# ============================================================================


@dataclass(frozen=True)
class Eligibility:
    min_age: int | None = None
    any_diagnosis_prefix: tuple[str, ...] | None = None

    def matches(self, patient: PatientSnapshot, as_of_date: date) -> bool:
        if self.min_age is not None:
            return patient.age >= self.min_age
        if self.any_diagnosis_prefix is not None:
            return _has_diagnosis_prefix(patient, self.any_diagnosis_prefix, as_of_date)
        return True


@dataclass(frozen=True)
class TierSignal:
    lab: str
    window_months: int


@dataclass(frozen=True)
class TierCondition:
    """One `when:` value. Exactly one "shape" is populated; the loader
    validates this at parse time. `gte`/`lt` may combine (moderate: gte+lt)."""

    gte: float | None = None
    lt: float | None = None
    no_result: bool = False
    default: bool = False
    any: tuple["TierCondition", ...] | None = None
    min_age: int | None = None
    diagnosis_prefix: tuple[str, ...] | None = None

    def matches(
        self,
        patient: PatientSnapshot,
        as_of_date: date,
        has_signal_result: bool,
        signal_value: float | None,
    ) -> bool:
        if self.default:
            return True
        if self.no_result:
            return not has_signal_result
        if self.any is not None:
            return any(
                c.matches(patient, as_of_date, has_signal_result, signal_value) for c in self.any
            )
        if self.min_age is not None:
            return patient.age >= self.min_age
        if self.diagnosis_prefix is not None:
            return _has_diagnosis_prefix(patient, self.diagnosis_prefix, as_of_date)
        if not has_signal_result:
            return False
        if self.gte is not None and signal_value < self.gte:
            return False
        if self.lt is not None and signal_value >= self.lt:
            return False
        return True


def _has_diagnosis_prefix(patient: PatientSnapshot, prefixes: tuple[str, ...], as_of_date: date) -> bool:
    prefix_tuple = tuple(prefixes)
    return any(
        is_past(d.diagnosed_date, as_of_date) and d.icd_code.startswith(prefix_tuple)
        for d in patient.diagnoses
    )


@dataclass(frozen=True)
class Tier:
    name: str
    when: TierCondition
    needs: dict[str, int]  # specialty -> cadence_days


@dataclass(frozen=True)
class ProgramDefinition:
    program_id: str
    version: int
    eligibility: Eligibility
    tier_signal: TierSignal | None
    tiers: tuple[Tier, ...]


# ============================================================================
# Outputs
# ============================================================================


@dataclass(frozen=True)
class NeedResult:
    specialty: str
    cadence_days: int
    last_visit_date: date | None
    due_date: date | None
    has_upcoming: bool
    decision: str  # no_task | scheduling | referral


@dataclass(frozen=True)
class ProgramResult:
    program_id: str
    eligible: bool
    tier: str | None
    needs: tuple[NeedResult, ...]


# ============================================================================
# Evaluation
# ============================================================================


def _tier_signal_value(
    patient: PatientSnapshot, signal: TierSignal, as_of_date: date
) -> tuple[bool, float | None]:
    lower_bound = months_before(as_of_date, signal.window_months)
    candidates = [
        lab
        for lab in patient.labs
        if lab.test_name == signal.lab and lower_bound <= lab.result_date <= as_of_date
    ]
    if not candidates:
        return False, None
    latest = max(candidates, key=lambda lab: lab.result_date)
    return True, latest.result_value


def _evaluate_need(
    patient: PatientSnapshot,
    specialty: str,
    cadence_days: int,
    as_of_date: date,
    primary_care_specialties: frozenset[str],
) -> NeedResult:
    past = [e for e in patient.encounters if e.specialty == specialty and is_past(e.encounter_date, as_of_date)]
    upcoming = [
        e for e in patient.encounters if e.specialty == specialty and not is_past(e.encounter_date, as_of_date)
    ]
    last_visit_date = max((e.encounter_date for e in past), default=None)

    if upcoming:
        return NeedResult(specialty, cadence_days, last_visit_date, None, True, "no_task")

    if not past:
        decision = "no_task" if specialty in primary_care_specialties else "referral"
        return NeedResult(specialty, cadence_days, None, None, False, decision)

    due_date = add_days(last_visit_date, cadence_days)
    gap_days = (as_of_date - last_visit_date).days
    decision = "scheduling" if gap_days > cadence_days else "no_task"
    return NeedResult(specialty, cadence_days, last_visit_date, due_date, False, decision)


def evaluate_program(
    patient: PatientSnapshot,
    program: ProgramDefinition,
    as_of_date: date,
    primary_care_specialties: frozenset[str],
) -> ProgramResult:
    if not program.eligibility.matches(patient, as_of_date):
        return ProgramResult(program.program_id, eligible=False, tier=None, needs=())

    has_signal_result = False
    signal_value: float | None = None
    if program.tier_signal is not None:
        has_signal_result, signal_value = _tier_signal_value(patient, program.tier_signal, as_of_date)

    winning_tier: Tier | None = None
    for tier in program.tiers:
        if tier.when.matches(patient, as_of_date, has_signal_result, signal_value):
            winning_tier = tier
            break
    if winning_tier is None:
        raise ValueError(
            f"no tier matched for program {program.program_id!r} -- "
            "the program definition has a gap in its tier conditions"
        )

    needs = tuple(
        _evaluate_need(patient, specialty, cadence_days, as_of_date, primary_care_specialties)
        for specialty, cadence_days in winning_tier.needs.items()
    )
    return ProgramResult(program.program_id, eligible=True, tier=winning_tier.name, needs=needs)


def evaluate_patient(
    patient: PatientSnapshot,
    programs: list[ProgramDefinition],
    as_of_date: date,
    primary_care_specialties: frozenset[str] = frozenset({"PCP"}),
) -> list[ProgramResult]:
    return [evaluate_program(patient, program, as_of_date, primary_care_specialties) for program in programs]
