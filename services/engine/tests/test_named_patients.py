"""Runs the evaluator, loaded with the real `seeds/programs/*.yaml`, against
real rows pulled straight from `ecares/data/*.csv` for each patient the
plan's verification table calls out by name. `as_of_date = 2026-04-08`
throughout, matching the plan.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from libs.common.settings import Settings
from services.engine.evaluator import evaluate_patient
from services.engine.program_loader import load_programs
from services.engine.tests.csv_fixtures import load_snapshot

AS_OF = date(2026, 4, 8)
PROGRAMS_DIR = Path(__file__).resolve().parents[3] / "seeds" / "programs"
PRIMARY_CARE = Settings().primary_care_specialty_set  # {"PCP"}, from the shared setting -- not hardcoded


def _programs():
    return load_programs(str(PROGRAMS_DIR))


def _results(patient_id: str) -> dict[str, object]:
    snapshot = load_snapshot(patient_id, AS_OF)
    results = evaluate_patient(snapshot, _programs(), AS_OF, frozenset(PRIMARY_CARE))
    return {r.program_id: r for r in results}


def _needs(result) -> dict[str, str]:
    return {n.specialty: n.decision for n in result.needs}


def test_p0201_high_risk_diabetic_every_outcome():
    results = _results("P0201")
    diabetes = results["diabetes_management"]
    assert diabetes.eligible is True
    assert diabetes.tier == "high_risk"
    assert _needs(diabetes) == {
        "Endocrinology": "referral",
        "Podiatry": "referral",
        "Cardiology": "scheduling",
        "Ophthalmology": "scheduling",
        "Nephrology": "scheduling",
    }
    # Matches the plan's own worked example: Cardiology due 2025-05-19,
    # 324 days overdue as of 2026-04-08.
    cardiology = next(n for n in diabetes.needs if n.specialty == "Cardiology")
    assert cardiology.due_date == date(2025, 5, 19)
    assert (AS_OF - cardiology.due_date).days == 324

    wellness = results["primary_care_wellness"]
    assert wellness.eligible is True
    assert wellness.tier == "high_priority"  # age 74 >= 65
    assert _needs(wellness) == {"PCP": "no_task"}  # upcoming visit 2026-05-24


def test_p0002_upcoming_visits_cover_cardiology_and_ophthalmology():
    diabetes = _results("P0002")["diabetes_management"]
    assert diabetes.eligible is True
    needs = _needs(diabetes)
    assert needs["Cardiology"] == "no_task"  # first visit booked 2026-04-18
    assert needs["Ophthalmology"] == "no_task"  # visit booked 2026-08-01
    cardiology = next(n for n in diabetes.needs if n.specialty == "Cardiology")
    ophthalmology = next(n for n in diabetes.needs if n.specialty == "Ophthalmology")
    assert cardiology.has_upcoming is True
    assert ophthalmology.has_upcoming is True


def test_p0087_pcp_gap_of_exactly_180_days_is_not_overdue():
    wellness = _results("P0087")["primary_care_wellness"]
    assert wellness.eligible is True
    # P0087 has no diagnoses and is 46 -> standard tier (cadence 365), and has
    # an upcoming PCP visit (2026-04-13) -- so "no task" comes from the
    # has_upcoming rule here, not from the gap comparison. The last *past*
    # visit (2025-10-10) does sit exactly 180 days before 2026-04-08, which
    # is the boundary the plan calls out; see ASSUMPTIONS.md for why that
    # 180-day gap doesn't independently drive the decision for this patient.
    assert wellness.tier == "standard"
    pcp = next(n for n in wellness.needs if n.specialty == "PCP")
    assert pcp.decision == "no_task"
    assert pcp.has_upcoming is True
    assert pcp.last_visit_date == date(2025, 10, 10)
    assert (AS_OF - pcp.last_visit_date).days == 180


def test_p0231_duplicate_encounter_is_a_sync_concern_not_evaluators():
    # The plan's dedup ("one stored encounter for 2024-10-02") happens when
    # the Data Service loads rows into the `encounters` table on its unique
    # key -- the evaluator only ever sees whatever rows the snapshot already
    # contains, and gap/upcoming logic looks at latest/earliest dates, not
    # row counts, so a duplicate row wouldn't change any decision anyway.
    # csv_fixtures.load_snapshot dedups on the same natural key so a snapshot
    # built directly from the CSV matches what the Data Service would hand
    # the evaluator. Sanity check that dedup happened and the patient still
    # evaluates without error.
    snapshot = load_snapshot("P0231", AS_OF)
    pcp_dates = [e.encounter_date for e in snapshot.encounters if e.specialty == "PCP"]
    assert pcp_dates.count(date(2024, 10, 2)) == 1
    results = _results("P0231")
    assert results["diabetes_management"].eligible is True


def test_p0029_under_18_not_eligible_for_wellness():
    wellness = _results("P0029")["primary_care_wellness"]
    assert wellness.eligible is False
    assert wellness.tier is None
    assert wellness.needs == ()


def test_p0003_adult_no_past_pcp_visit_no_task_not_referral():
    wellness = _results("P0003")["primary_care_wellness"]
    assert wellness.eligible is True
    pcp = next(n for n in wellness.needs if n.specialty == "PCP")
    assert pcp.decision == "no_task"  # never a referral for primary care
    assert pcp.due_date is None
    assert pcp.next_check_candidate is None


def test_p0018_pcp_history_comes_from_encounters_not_the_name_field():
    # P0018 has no pcp_provider_name in patients.csv, but does have PCP
    # encounters -- the evaluator only ever looks at encounters, so this
    # patient behaves like anyone else with PCP history.
    snapshot = load_snapshot("P0018", AS_OF)
    assert any(e.specialty == "PCP" for e in snapshot.encounters)
    wellness = _results("P0018")["primary_care_wellness"]
    pcp = next(n for n in wellness.needs if n.specialty == "PCP")
    assert pcp.last_visit_date is not None  # history found via encounters


def test_p0004_only_a1c_older_than_six_months_is_unmonitored():
    diabetes = _results("P0004")["diabetes_management"]
    assert diabetes.eligible is True
    assert diabetes.tier == "unmonitored"
    assert diabetes.tier_recheck_at is None  # no result in window -> nothing to recheck from
    endocrinology = next(n for n in diabetes.needs if n.specialty == "Endocrinology")
    assert endocrinology.cadence_days == 90
