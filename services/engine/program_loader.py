"""Parses `seeds/programs/*.yaml` into the dataclasses `evaluator.py` expects,
and converts to/from the `ProgramDefinition` proto message (`definition_json`
= the parsed structure re-serialized as JSON -- see CLAUDE.md decision #9).

Validates shape lightly and fails loudly (raises) on a malformed program
file: a half-loaded rule set is worse than a crash at startup.
"""

from __future__ import annotations

import json
from glob import glob
from pathlib import Path

import yaml

from libs.common.grpc_gen import dataservice_pb2
from services.engine.evaluator import (
    Eligibility,
    ProgramDefinition,
    Tier,
    TierCondition,
    TierSignal,
)


class ProgramLoadError(ValueError):
    """Raised on a malformed program definition -- fail loudly at startup."""


# ---------------------------------------------------------------------------
# YAML / dict -> dataclasses
# ---------------------------------------------------------------------------


def _parse_condition(raw: object) -> TierCondition:
    if raw == "no_result":
        return TierCondition(no_result=True)
    if raw == "default":
        return TierCondition(default=True)
    if isinstance(raw, dict):
        if "any" in raw:
            return TierCondition(any=tuple(_parse_condition(c) for c in raw["any"]))
        if "min_age" in raw:
            return TierCondition(min_age=int(raw["min_age"]))
        if "diagnosis_prefix" in raw:
            return TierCondition(diagnosis_prefix=tuple(str(p) for p in raw["diagnosis_prefix"]))
        if "gte" in raw or "lt" in raw:
            return TierCondition(
                gte=float(raw["gte"]) if "gte" in raw else None,
                lt=float(raw["lt"]) if "lt" in raw else None,
            )
    raise ProgramLoadError(f"unrecognized tier condition: {raw!r}")


def _condition_to_dict(cond: TierCondition) -> object:
    if cond.default:
        return "default"
    if cond.no_result:
        return "no_result"
    if cond.any is not None:
        return {"any": [_condition_to_dict(c) for c in cond.any]}
    if cond.min_age is not None:
        return {"min_age": cond.min_age}
    if cond.diagnosis_prefix is not None:
        return {"diagnosis_prefix": list(cond.diagnosis_prefix)}
    d: dict[str, float] = {}
    if cond.gte is not None:
        d["gte"] = cond.gte
    if cond.lt is not None:
        d["lt"] = cond.lt
    return d


def _parse_eligibility(raw: dict | None) -> Eligibility:
    if not raw:
        return Eligibility()
    if "min_age" in raw:
        return Eligibility(min_age=int(raw["min_age"]))
    if "any_diagnosis_prefix" in raw:
        return Eligibility(any_diagnosis_prefix=tuple(str(p) for p in raw["any_diagnosis_prefix"]))
    raise ProgramLoadError(f"unrecognized eligibility block: {raw!r}")


def _eligibility_to_dict(elig: Eligibility) -> dict | None:
    if elig.min_age is not None:
        return {"min_age": elig.min_age}
    if elig.any_diagnosis_prefix is not None:
        return {"any_diagnosis_prefix": list(elig.any_diagnosis_prefix)}
    return None


def _parse_tier_signal(raw: dict | None) -> TierSignal | None:
    if not raw:
        return None
    try:
        return TierSignal(lab=raw["lab"], window_months=int(raw["window_months"]))
    except KeyError as exc:
        raise ProgramLoadError(f"tier_signal missing required key {exc}: {raw!r}") from exc


def _parse_tier(raw: dict) -> Tier:
    for key in ("name", "when", "needs"):
        if key not in raw:
            raise ProgramLoadError(f"tier missing required key {key!r}: {raw!r}")
    needs = {str(specialty): int(cadence) for specialty, cadence in raw["needs"].items()}
    if not needs:
        raise ProgramLoadError(f"tier {raw['name']!r} has no needs")
    return Tier(name=str(raw["name"]), when=_parse_condition(raw["when"]), needs=needs)


def program_from_dict(raw: dict) -> ProgramDefinition:
    for key in ("program_id", "version", "tiers"):
        if key not in raw:
            raise ProgramLoadError(f"program definition missing required key {key!r}: {raw!r}")
    tiers_raw = raw["tiers"]
    if not tiers_raw:
        raise ProgramLoadError(f"program {raw['program_id']!r} has no tiers")
    return ProgramDefinition(
        program_id=str(raw["program_id"]),
        version=int(raw["version"]),
        eligibility=_parse_eligibility(raw.get("eligibility")),
        tier_signal=_parse_tier_signal(raw.get("tier_signal")),
        tiers=tuple(_parse_tier(t) for t in tiers_raw),
    )


def program_to_dict(program: ProgramDefinition) -> dict:
    d: dict = {"program_id": program.program_id, "version": program.version}
    eligibility = _eligibility_to_dict(program.eligibility)
    if eligibility is not None:
        d["eligibility"] = eligibility
    if program.tier_signal is not None:
        d["tier_signal"] = {
            "lab": program.tier_signal.lab,
            "window_months": program.tier_signal.window_months,
        }
    d["tiers"] = [
        {"name": t.name, "when": _condition_to_dict(t.when), "needs": dict(t.needs)}
        for t in program.tiers
    ]
    return d


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------


def load_programs(programs_dir: str) -> list[ProgramDefinition]:
    """Parses every `*.yaml` file in `programs_dir` (sorted, for repeatable
    order). Each file may hold one or more `---`-separated documents;
    `safe_load_all` handles both shapes."""
    programs: list[ProgramDefinition] = []
    for path in sorted(glob(str(Path(programs_dir) / "*.yaml"))):
        with open(path, encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
        if not docs or all(d is None for d in docs):
            raise ProgramLoadError(f"{path} contains no program document")
        for doc in docs:
            if doc is None:
                continue
            try:
                programs.append(program_from_dict(doc))
            except ProgramLoadError as exc:
                raise ProgramLoadError(f"{path}: {exc}") from exc
    return programs


# ---------------------------------------------------------------------------
# Proto conversion (definition_json, per CLAUDE.md decision #9)
# ---------------------------------------------------------------------------


def to_proto_program(program: ProgramDefinition, *, active: bool = True) -> dataservice_pb2.ProgramDefinition:
    return dataservice_pb2.ProgramDefinition(
        program_id=program.program_id,
        version=program.version,
        definition_json=json.dumps(program_to_dict(program)),
        active=active,
    )


def from_proto_program(msg: dataservice_pb2.ProgramDefinition) -> ProgramDefinition:
    return program_from_dict(json.loads(msg.definition_json))
