"""Parses `programs/*.yaml` into the dataclasses `evaluator.py` expects.

Trimmed from `main`'s `services/engine/program_loader.py`: that version also
round-tripped definitions through a proto message so a separate Data Service
could read them back from its own DB. There's no separate service here, so
programs just live as YAML and get read into memory -- one function, one
direction, nothing to serialize back out.
"""

from __future__ import annotations

from glob import glob
from pathlib import Path

import yaml

from app.engine.evaluator import Eligibility, ProgramDefinition, Tier, TierCondition, TierSignal


class ProgramLoadError(ValueError):
    """Raised on a malformed program definition -- fail loudly at startup."""


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


def _parse_eligibility(raw: dict | None) -> Eligibility:
    if not raw:
        return Eligibility()
    if "min_age" in raw:
        return Eligibility(min_age=int(raw["min_age"]))
    if "any_diagnosis_prefix" in raw:
        return Eligibility(any_diagnosis_prefix=tuple(str(p) for p in raw["any_diagnosis_prefix"]))
    raise ProgramLoadError(f"unrecognized eligibility block: {raw!r}")


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


def load_programs(programs_dir: str) -> list[ProgramDefinition]:
    """Parses every `*.yaml` file in `programs_dir` (sorted, for repeatable
    order). Adding a new program is dropping a new file here -- nothing
    else changes. Each file may hold one or more `---`-separated documents."""
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
