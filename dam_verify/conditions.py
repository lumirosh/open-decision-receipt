"""Authority-bound per-condition checks with separate mutable observations."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .receipt import sha256_of

HOLDING = "holding"
BREACHED = "breached"
STALE = "stale"
UNKNOWN = "unknown"
_STATE_ORDER = {UNKNOWN: 0, STALE: 1, BREACHED: 2, HOLDING: 3}


def condition_id(definition: dict) -> str | None:
    """Accept the RC3 prototype's name while emitting the public condition_id."""
    return definition.get("condition_id") or definition.get("name")


def condition_definition_hash(definitions: list[dict]) -> str:
    canonical = sorted(
        json.dumps(d, sort_keys=True, separators=(",", ":"))
        for d in canonical_condition_definitions(definitions)
    )
    return sha256_of(canonical)


def canonical_condition_definitions(definitions: list[dict]) -> list[dict]:
    """Normalize the temporary local aliases before hashing/binding authority."""
    normalized = []
    for definition in definitions:
        item = dict(definition)
        item["condition_id"] = item.pop("condition_id", None) or item.pop("name", None)
        item.pop("name", None)
        item["source_ref"] = item.pop("source_ref", None) or item.pop("ref", None)
        item.pop("ref", None)
        normalized.append(item)
    return normalized


def _utc(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def evaluate_condition(definition: dict, observation: dict | None, evaluated_at: str) -> str:
    """Evaluate the only supported primitive, equality, failing closed on ambiguity."""
    if observation is None or definition.get("operator", "eq") != "eq":
        return UNKNOWN
    evaluated = _utc(evaluated_at)
    validated = _utc(observation.get("last_validated_at"))
    if evaluated is None or validated is None or validated > evaluated:
        return UNKNOWN
    max_age = definition.get("max_age_seconds")
    if not isinstance(max_age, int) or isinstance(max_age, bool) or max_age < 0:
        return UNKNOWN
    if (evaluated - validated).total_seconds() > max_age:
        return STALE
    if "observed_value" not in observation or "expected_value" not in definition:
        return UNKNOWN
    return HOLDING if observation["observed_value"] == definition["expected_value"] else BREACHED


def _detail(definition: dict, observation: dict | None, state: str) -> dict:
    cid = condition_id(definition)
    return {
        "condition_id": cid,
        "name": cid,  # compatibility with the first local test slice
        "source_ref": definition.get("source_ref") or definition.get("ref"),
        "ref": definition.get("source_ref") or definition.get("ref"),
        "operator": definition.get("operator", "eq"),
        "state": state,
        "observed_value": (observation or {}).get("observed_value"),
        "expected": definition.get("expected_value"),
        "expected_value": definition.get("expected_value"),
        "last_validated_at": (observation or {}).get("last_validated_at"),
        "max_age_seconds": definition.get("max_age_seconds"),
    }


def _valid_compensation(compensation: dict | None, ids: set[str]) -> bool:
    if compensation is None:
        return True
    if not isinstance(compensation, dict) or compensation.get("mode") != "k_of_n":
        return False
    members = compensation.get("members")
    k = compensation.get("k")
    return (
        isinstance(members, list)
        and len(members) == len(set(members))
        and set(members) == ids
        and isinstance(k, int)
        and not isinstance(k, bool)
        and 1 <= k <= len(members)
    )


def evaluate_conditions(
    definitions: list[dict],
    observations: dict[str, dict],
    evaluated_at: str,
    compensation: dict | None = None,
    authority_hash: str | None = None,
) -> dict:
    ids = [condition_id(d) for d in definitions]
    valid_definitions = bool(definitions) and None not in ids and len(ids) == len(set(ids))
    per: dict[str, dict] = {}
    aggregate = HOLDING
    for definition in definitions:
        cid = condition_id(definition)
        ref = definition.get("source_ref") or definition.get("ref")
        state = evaluate_condition(definition, observations.get(ref), evaluated_at)
        if cid is not None:
            per[cid] = _detail(definition, observations.get(ref), state)
        if _STATE_ORDER[state] < _STATE_ORDER[aggregate]:
            aggregate = state
    if not valid_definitions:
        aggregate = UNKNOWN

    ids_set = {i for i in ids if i is not None}
    comp_valid = _valid_compensation(compensation, ids_set)
    holding_count = sum(d["state"] == HOLDING for d in per.values())
    applied = (
        bool(compensation)
        and comp_valid
        and aggregate != UNKNOWN
        and holding_count >= compensation["k"]
    )
    holds = aggregate == HOLDING or applied
    return {
        "definition_hash": condition_definition_hash(definitions),
        "evaluated_at": evaluated_at,
        "aggregate": aggregate,
        "holds": holds,
        "conditions": per,
        "compensation": {
            "mode": (compensation or {}).get("mode", "none"),
            "valid": comp_valid,
            "applied": applied,
            "authority_hash": authority_hash if compensation else None,
        },
    }


def failed_conditions(result: dict) -> list[dict]:
    return [d for d in result["conditions"].values() if d["state"] != HOLDING]


def holding_condition_ids(result: dict) -> list[str]:
    return sorted(d["condition_id"] for d in result["conditions"].values() if d["state"] == HOLDING)


def condition_refs(definitions: list[dict]) -> list[str]:
    return sorted({ref for d in definitions if (ref := d.get("source_ref") or d.get("ref"))})


def compensation_refused(request_comp: dict | None, rule: dict, definitions: list[dict] | None = None) -> bool:
    """Only the exact, valid compensation rule inside approved authority may apply."""
    bound = rule.get("compensation")
    ids = {condition_id(d) for d in (definitions or [])}
    if bound is not None and not _valid_compensation(bound, {i for i in ids if i is not None}):
        return True
    if request_comp is None:
        return False
    return bound is None or request_comp != bound


class ObservationsStore:
    """Mutable observation snapshots, separate from immutable authority definitions."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def resolve(self, workflow: str) -> dict | None:
        path = self.root / f"{workflow}.yaml"
        return yaml.safe_load(path.read_text()) if path.exists() else None

    def observations_for(self, workflow: str, refs: list[str]) -> dict[str, dict]:
        snapshots = (self.resolve(workflow) or {}).get("observations", {}) or {}
        return {ref: snapshots[ref] for ref in refs if ref in snapshots}
