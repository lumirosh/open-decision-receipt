import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "decision-receipt.schema.json").read_text())
BASE = yaml.safe_load((ROOT / "examples" / "claim-payout-receipt.yaml").read_text())


def condition_check(state="stale"):
    return {
        "definition_hash": "sha256:" + "a" * 64,
        "evaluated_at": "2026-08-17T12:00:00Z",
        "aggregate": state,
        "holds": False,
        "conditions": {
            "vendor-attestation": {
                "condition_id": "vendor-attestation",
                "source_ref": "evidence://vendor-attestation",
                "operator": "eq",
                "state": state,
                "observed_value": "valid",
                "expected": "valid",
                "last_validated_at": "2026-08-16T06:00:00Z",
                "max_age_seconds": 86400,
            }
        },
        "compensation": {"mode": "none", "valid": True, "applied": False, "authority_hash": None},
    }


def test_schema_accepts_structured_condition_check():
    receipt = dict(BASE)
    receipt["check"] = dict(BASE["check"]) | {"conditions": condition_check()}
    assert list(Draft202012Validator(SCHEMA).iter_errors(receipt)) == []


def test_schema_rejects_invalid_condition_state_when_conditions_are_present():
    receipt = dict(BASE)
    receipt["check"] = dict(BASE["check"]) | {"conditions": condition_check("maybe")}
    errors = list(Draft202012Validator(SCHEMA).iter_errors(receipt))
    assert any("'maybe' is not one of" in error.message for error in errors)


def test_schema_accepts_fail_closed_unknown_with_invalid_definition_details():
    receipt = dict(BASE)
    check = condition_check("unknown")
    item = check["conditions"]["vendor-attestation"]
    item["operator"] = "unsupported"
    item["max_age_seconds"] = None
    receipt["check"] = dict(BASE["check"]) | {"conditions": check}
    assert list(Draft202012Validator(SCHEMA).iter_errors(receipt)) == []
