"""Unit tests for the pure evaluator: tier boundary math, no_result/default/any
conditions, the strict overdue boundary, and eligibility -- against small,
synthetic programs and patients (not the real YAML; see test_program_loader.py
and test_named_patients.py for that)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from services.engine.evaluator import (
    Diagnosis,
    Encounter,
    Eligibility,
    LabResult,
    PatientSnapshot,
    ProgramDefinition,
    Tier,
    TierCondition,
    TierSignal,
    age_as_of,
    evaluate_patient,
    evaluate_program,
)

AS_OF = date(2026, 4, 8)
PCP = frozenset({"PCP"})


def _diabetes_program() -> ProgramDefinition:
    return ProgramDefinition(
        program_id="diabetes_management",
        version=1,
        eligibility=Eligibility(any_diagnosis_prefix=("E10", "E11")),
        tier_signal=TierSignal(lab="HbA1c", window_months=6),
        tiers=(
            Tier("high_risk", TierCondition(gte=9.0), {"Endocrinology": 90}),
            Tier("moderate", TierCondition(gte=7.0, lt=9.0), {"Endocrinology": 180}),
            Tier("low_risk", TierCondition(lt=7.0), {"Endocrinology": 365}),
            Tier("unmonitored", TierCondition(no_result=True), {"Endocrinology": 90}),
        ),
    )


def _diabetic_patient(a1c_value: float | None, a1c_date: date | None) -> PatientSnapshot:
    labs = [LabResult("HbA1c", a1c_value, a1c_date)] if a1c_value is not None else []
    return PatientSnapshot(
        patient_id="TEST",
        age=50,
        diagnoses=[Diagnosis("E11.9", date(2020, 1, 1))],
        labs=labs,
        encounters=[],
    )


# --- tier boundary math ------------------------------------------------


@pytest.mark.parametrize(
    "value,expected_tier",
    [
        (9.0, "high_risk"),  # gte 9.0 -> exactly on the high_risk boundary
        (8.999, "moderate"),
        (7.0, "moderate"),  # exactly on the moderate lower boundary
        (6.999, "low_risk"),
        (13.1, "high_risk"),
    ],
)
def test_tier_boundaries(value, expected_tier):
    patient = _diabetic_patient(value, date(2026, 1, 1))
    result = evaluate_program(patient, _diabetes_program(), AS_OF, PCP)
    assert result.tier == expected_tier


def test_no_result_tier_when_no_lab_at_all():
    patient = _diabetic_patient(None, None)
    result = evaluate_program(patient, _diabetes_program(), AS_OF, PCP)
    assert result.tier == "unmonitored"
    assert result.tier_recheck_at is None  # no signal found -> nothing to recheck from


def test_no_result_tier_when_lab_outside_window():
    # window is [2025-10-08, 2026-04-08]; this result is one day too old
    patient = _diabetic_patient(9.5, date(2025, 10, 7))
    result = evaluate_program(patient, _diabetes_program(), AS_OF, PCP)
    assert result.tier == "unmonitored"


def test_lab_on_window_lower_bound_is_included():
    patient = _diabetic_patient(9.5, date(2025, 10, 8))
    result = evaluate_program(patient, _diabetes_program(), AS_OF, PCP)
    assert result.tier == "high_risk"


def test_tier_recheck_at_set_only_when_signal_found():
    patient = _diabetic_patient(9.5, date(2026, 1, 15))
    result = evaluate_program(patient, _diabetes_program(), AS_OF, PCP)
    # result_date + 6 calendar months + 1 day
    assert result.tier_recheck_at == date(2026, 7, 16)


def test_tier_order_matters_first_match_wins():
    # A value of 9.0 satisfies both {gte: 9.0} and, if checked, would also be
    # >= a hypothetical lower-bound clause -- high_risk must win because it
    # is listed first, not because it's the only match.
    tiers_reordered = ProgramDefinition(
        program_id="x",
        version=1,
        eligibility=Eligibility(),
        tier_signal=TierSignal(lab="HbA1c", window_months=6),
        tiers=(
            Tier("catch_all", TierCondition(gte=0.0), {"Endocrinology": 90}),
            Tier("high_risk", TierCondition(gte=9.0), {"Endocrinology": 90}),
        ),
    )
    patient = _diabetic_patient(9.5, date(2026, 1, 1))
    result = evaluate_program(patient, tiers_reordered, AS_OF, PCP)
    assert result.tier == "catch_all"  # first match wins, even though high_risk also matches


# --- wellness default / any ---------------------------------------------


def _wellness_program() -> ProgramDefinition:
    return ProgramDefinition(
        program_id="primary_care_wellness",
        version=1,
        eligibility=Eligibility(min_age=18),
        tier_signal=None,
        tiers=(
            Tier(
                "high_priority",
                TierCondition(any=(TierCondition(min_age=65), TierCondition(diagnosis_prefix=("E10", "E11")))),
                {"PCP": 180},
            ),
            Tier("standard", TierCondition(default=True), {"PCP": 365}),
        ),
    )


def test_wellness_any_min_age_branch():
    patient = PatientSnapshot(patient_id="T", age=70, diagnoses=[], labs=[], encounters=[])
    result = evaluate_program(patient, _wellness_program(), AS_OF, PCP)
    assert result.tier == "high_priority"


def test_wellness_any_diagnosis_prefix_branch():
    patient = PatientSnapshot(
        patient_id="T", age=40, diagnoses=[Diagnosis("E11.40", date(2020, 1, 1))], labs=[], encounters=[]
    )
    result = evaluate_program(patient, _wellness_program(), AS_OF, PCP)
    assert result.tier == "high_priority"


def test_wellness_default_fallback():
    patient = PatientSnapshot(patient_id="T", age=40, diagnoses=[], labs=[], encounters=[])
    result = evaluate_program(patient, _wellness_program(), AS_OF, PCP)
    assert result.tier == "standard"


def test_wellness_ineligible_under_min_age():
    patient = PatientSnapshot(patient_id="T", age=17, diagnoses=[], labs=[], encounters=[])
    result = evaluate_program(patient, _wellness_program(), AS_OF, PCP)
    assert result.eligible is False
    assert result.tier is None
    assert result.needs == ()


def test_future_diagnosis_does_not_count_toward_eligibility_or_tier():
    # diagnosed_date after as_of_date must not count as "on or before as_of"
    patient = PatientSnapshot(
        patient_id="T", age=40, diagnoses=[Diagnosis("E11.40", date(2026, 4, 9))], labs=[], encounters=[]
    )
    result = evaluate_program(patient, _wellness_program(), AS_OF, PCP)
    assert result.tier == "standard"  # not high_priority, since the diagnosis isn't "past" yet


# --- needs / task decisions ----------------------------------------------


def _single_need_program(specialty: str, cadence: int) -> ProgramDefinition:
    return ProgramDefinition(
        program_id="p",
        version=1,
        eligibility=Eligibility(),
        tier_signal=None,
        tiers=(Tier("only", TierCondition(default=True), {specialty: cadence}),),
    )


def test_upcoming_visit_wins_over_gap_no_task():
    program = _single_need_program("Cardiology", 90)
    patient = PatientSnapshot(
        patient_id="T",
        age=40,
        diagnoses=[],
        labs=[],
        encounters=[Encounter("Cardiology", date(2020, 1, 1), is_upcoming=False), Encounter("Cardiology", date(2026, 5, 1))],
    )
    result = evaluate_program(patient, program, AS_OF, PCP)
    need = result.needs[0]
    assert need.decision == "no_task"
    assert need.has_upcoming is True
    assert need.next_check_candidate == date(2026, 5, 2)


def test_earliest_upcoming_used_when_several():
    program = _single_need_program("Cardiology", 90)
    patient = PatientSnapshot(
        patient_id="T",
        age=40,
        diagnoses=[],
        labs=[],
        encounters=[Encounter("Cardiology", date(2026, 8, 1)), Encounter("Cardiology", date(2026, 5, 1))],
    )
    result = evaluate_program(patient, program, AS_OF, PCP)
    assert result.needs[0].next_check_candidate == date(2026, 5, 2)


def test_no_past_visit_specialist_is_referral():
    program = _single_need_program("Endocrinology", 90)
    patient = PatientSnapshot(patient_id="T", age=40, diagnoses=[], labs=[], encounters=[])
    result = evaluate_program(patient, program, AS_OF, PCP)
    need = result.needs[0]
    assert need.decision == "referral"
    assert need.due_date is None
    assert need.next_check_candidate is None


def test_no_past_visit_primary_care_is_no_task_not_referral():
    program = _single_need_program("PCP", 365)
    patient = PatientSnapshot(patient_id="T", age=40, diagnoses=[], labs=[], encounters=[])
    result = evaluate_program(patient, program, AS_OF, PCP)
    need = result.needs[0]
    assert need.decision == "no_task"
    assert need.next_check_candidate is None


@pytest.mark.parametrize(
    "gap_days,expected_decision",
    [(179, "no_task"), (180, "no_task"), (181, "scheduling")],
)
def test_strict_overdue_boundary_generic(gap_days, expected_decision):
    cadence = 180
    last_visit = date(2026, 4, 8) - timedelta(days=gap_days)
    program = _single_need_program("PCP", cadence)
    patient = PatientSnapshot(
        patient_id="T", age=40, diagnoses=[], labs=[], encounters=[Encounter("PCP", last_visit)]
    )
    result = evaluate_program(patient, program, AS_OF, PCP)
    need = result.needs[0]
    assert need.decision == expected_decision
    assert need.due_date == last_visit + timedelta(days=cadence)
    assert need.next_check_candidate == need.due_date + timedelta(days=1)


# --- eligibility ----------------------------------------------------------


def test_no_eligibility_block_means_eligible_by_default():
    program = ProgramDefinition(
        program_id="p",
        version=1,
        eligibility=Eligibility(),
        tier_signal=None,
        tiers=(Tier("only", TierCondition(default=True), {}),),
    )
    patient = PatientSnapshot(patient_id="T", age=1, diagnoses=[], labs=[], encounters=[])
    result = evaluate_program(patient, program, AS_OF, PCP)
    assert result.eligible is True


def test_age_as_of_is_birthday_aware():
    assert age_as_of(date(2000, 4, 8), date(2026, 4, 8)) == 26  # birthday is today -> already had it
    assert age_as_of(date(2000, 4, 9), date(2026, 4, 8)) == 25  # birthday is tomorrow -> not yet


def test_evaluate_patient_runs_every_program_independently():
    results = evaluate_patient(
        PatientSnapshot(patient_id="T", age=70, diagnoses=[], labs=[], encounters=[]),
        [_wellness_program(), _diabetes_program()],
        AS_OF,
        PCP,
    )
    assert len(results) == 2
    assert results[0].program_id == "primary_care_wellness"
    assert results[1].program_id == "diabetes_management"
    assert results[1].eligible is False  # no diabetes diagnosis
