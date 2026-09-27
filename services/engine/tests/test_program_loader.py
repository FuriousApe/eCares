"""Parses the real `seeds/programs/*.yaml` files and checks the resulting
dataclasses match the plan's schema, and that they round-trip through the
JSON encoding sent over `UpsertPrograms`/`ListPrograms` without loss."""

from __future__ import annotations

import json
from pathlib import Path

from services.engine.evaluator import TierCondition
from services.engine.program_loader import (
    from_proto_program,
    load_programs,
    program_from_dict,
    program_to_dict,
    to_proto_program,
)

PROGRAMS_DIR = Path(__file__).resolve().parents[3] / "seeds" / "programs"


def _load():
    return {p.program_id: p for p in load_programs(str(PROGRAMS_DIR))}


def test_loads_both_real_program_files():
    programs = _load()
    assert set(programs) == {"diabetes_management", "primary_care_wellness"}


def test_diabetes_program_shape():
    p = _load()["diabetes_management"]
    assert p.version == 1
    assert p.eligibility.any_diagnosis_prefix == ("E10", "E11")
    assert p.tier_signal.lab == "HbA1c"
    assert p.tier_signal.window_months == 6
    names = [t.name for t in p.tiers]
    assert names == ["high_risk", "moderate", "low_risk", "unmonitored"]

    high_risk, moderate, low_risk, unmonitored = p.tiers
    assert high_risk.when == TierCondition(gte=9.0)
    assert high_risk.needs == {
        "Endocrinology": 90,
        "Cardiology": 90,
        "Podiatry": 180,
        "Ophthalmology": 365,
        "Nephrology": 180,
    }
    assert moderate.when == TierCondition(gte=7.0, lt=9.0)
    assert moderate.needs == {"Endocrinology": 180, "Ophthalmology": 365, "Podiatry": 365}
    assert low_risk.when == TierCondition(lt=7.0)
    assert low_risk.needs == {"Endocrinology": 365, "Ophthalmology": 365}
    assert unmonitored.when == TierCondition(no_result=True)
    assert unmonitored.needs == {"Endocrinology": 90}


def test_wellness_program_shape():
    p = _load()["primary_care_wellness"]
    assert p.version == 1
    assert p.eligibility.min_age == 18
    assert p.tier_signal is None
    names = [t.name for t in p.tiers]
    assert names == ["high_priority", "standard"]

    high_priority, standard = p.tiers
    assert high_priority.when.any is not None
    assert high_priority.when.any[0] == TierCondition(min_age=65)
    assert high_priority.when.any[1] == TierCondition(
        diagnosis_prefix=("E10", "E11", "I10", "E78", "J45", "N18", "I25", "E03", "G47.3", "M81")
    )
    assert high_priority.needs == {"PCP": 180}
    assert standard.when == TierCondition(default=True)
    assert standard.needs == {"PCP": 365}


def test_round_trips_through_json_without_loss():
    for program in _load().values():
        as_dict = program_to_dict(program)
        json_text = json.dumps(as_dict)
        rebuilt = program_from_dict(json.loads(json_text))
        assert rebuilt == program


def test_round_trips_through_proto_message():
    for program in _load().values():
        msg = to_proto_program(program)
        assert msg.program_id == program.program_id
        assert msg.version == program.version
        assert msg.active is True
        rebuilt = from_proto_program(msg)
        assert rebuilt == program
