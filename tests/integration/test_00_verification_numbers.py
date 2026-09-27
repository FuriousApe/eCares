"""Live-system check of the plan's Verification section: the two headline
totals (scheduler sees 154 tasks, clinical sees 273) and the eight
named-patient edge cases, read back through the real REST API -- or, for the
one case the API can't express (P0231's raw encounter dedup, since there is
no `GET /encounters`), a direct MySQL read.

**Ordering note.** These totals assume the `tasks` table still looks exactly
like a fresh `make seed` produced (every task `open`, nothing claimed,
declined or snoozed yet). Other files in this suite (decline, concurrency,
failure, time-travel) deliberately mutate task state and/or `AS_OF_DATE`, and
restore the baseline at the end of each -- but a shared, stateful live stack
is not the same as a hermetic test. This file is named to collect first
(pytest's default alphabetical file order sorts `00_verification` before
every letter), and for the cleanest possible signal you can also just run it
alone right after `make seed`:

    pytest tests/integration/test_00_verification_numbers.py
"""

from __future__ import annotations

from datetime import date

import httpx
import sqlalchemy as sa


def _paginate_tasks(client: httpx.Client, **params) -> list[dict]:
    items: list[dict] = []
    cursor = None
    while True:
        page_params = dict(params, limit=200)
        if cursor:
            page_params["cursor"] = cursor
        resp = client.get("/tasks", params=page_params)
        resp.raise_for_status()
        body = resp.json()
        items.extend(body["items"])
        cursor = body.get("next_cursor")
        if not cursor:
            return items


def test_scheduler_sees_154_scheduling_tasks(scheduler_client):
    items = _paginate_tasks(scheduler_client)
    assert len(items) == 154
    assert all(t["task_type"] == "scheduling" for t in items)


def test_clinical_sees_273_tasks(clinical_client):
    items = _paginate_tasks(clinical_client)
    assert len(items) == 273


def _visible_tasks_by_specialty(client: httpx.Client, patient_id: str) -> dict[str, str]:
    resp = client.get(f"/patients/{patient_id}")
    resp.raise_for_status()
    return {t["specialty"]: t["task_type"] for t in resp.json()["visible_tasks"]}


def test_p0201_high_risk_diabetic_every_outcome(clinical_client):
    by_specialty = _visible_tasks_by_specialty(clinical_client, "P0201")
    assert by_specialty == {
        "Endocrinology": "referral",
        "Podiatry": "referral",
        "Cardiology": "scheduling",
        "Ophthalmology": "scheduling",
        "Nephrology": "scheduling",
    }


def test_p0002_upcoming_visits_cover_cardiology_and_ophthalmology(clinical_client):
    by_specialty = _visible_tasks_by_specialty(clinical_client, "P0002")
    assert "Cardiology" not in by_specialty
    assert "Ophthalmology" not in by_specialty


def test_p0087_pcp_gap_of_exactly_180_days_no_task(clinical_client):
    by_specialty = _visible_tasks_by_specialty(clinical_client, "P0087")
    assert "PCP" not in by_specialty


def test_p0231_duplicate_encounter_deduped_in_storage(mysql_engine):
    # The REST API has no encounters endpoint, so this is the one named-patient
    # check that has to go straight to MySQL rather than through the API.
    with mysql_engine.connect() as conn:
        count = conn.execute(
            sa.text("SELECT COUNT(*) FROM encounters WHERE patient_id=:p AND encounter_date=:d"),
            {"p": "P0231", "d": date(2024, 10, 2)},
        ).scalar_one()
    assert count == 1


def test_p0029_under_18_no_wellness_enrollment(clinical_client):
    resp = clinical_client.get("/patients/P0029")
    resp.raise_for_status()
    program_ids = {e["program_id"] for e in resp.json()["enrollments"]}
    assert "primary_care_wellness" not in program_ids


def test_p0003_adult_no_past_pcp_visit_no_task(clinical_client):
    by_specialty = _visible_tasks_by_specialty(clinical_client, "P0003")
    assert "PCP" not in by_specialty


def test_p0018_pcp_history_comes_from_encounters(clinical_client):
    resp = clinical_client.get("/patients/P0018")
    resp.raise_for_status()
    needs = resp.json()["needs"]
    pcp_need = next(n for n in needs if n["specialty"] == "PCP")
    assert pcp_need["last_visit_date"] is not None


def test_p0004_unmonitored_tier(clinical_client):
    resp = clinical_client.get("/patients/P0004")
    resp.raise_for_status()
    tiers_by_program = {e["program_id"]: e["tier"] for e in resp.json()["enrollments"]}
    assert tiers_by_program.get("diabetes_management") == "unmonitored"
