import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_SCHEMA = ROOT / "schemas" / "decision-receipt.schema.json"
ACTION_SCHEMA = ROOT / "schemas" / "action-request.schema.json"


def load_json(path):
    return json.loads(path.read_text())


def load_yaml(path):
    return yaml.safe_load(path.read_text())


def test_decision_receipt_schema_is_valid_json_schema():
    Draft202012Validator.check_schema(load_json(RECEIPT_SCHEMA))


def test_action_request_schema_is_valid_json_schema():
    Draft202012Validator.check_schema(load_json(ACTION_SCHEMA))


@pytest.mark.parametrize(
    "example",
    [
        ROOT / "examples" / "claim-payout-receipt.yaml",
        ROOT / "examples" / "gift-card-fraud-no-receipt.yaml",
    ],
)
def test_receipt_examples_validate_against_schema(example):
    validator = Draft202012Validator(load_json(RECEIPT_SCHEMA))
    errors = sorted(validator.iter_errors(load_yaml(example)), key=lambda e: e.path)
    assert errors == []


def test_action_request_example_validates_against_schema():
    validator = Draft202012Validator(load_json(ACTION_SCHEMA))
    errors = sorted(
        validator.iter_errors(load_json(ROOT / "examples" / "verify-action-deploy.json")),
        key=lambda e: e.path,
    )
    assert errors == []


def test_receipt_schema_rejects_missing_required_block():
    receipt = load_yaml(ROOT / "examples" / "claim-payout-receipt.yaml")
    receipt.pop("authority")
    errors = list(Draft202012Validator(load_json(RECEIPT_SCHEMA)).iter_errors(receipt))
    assert any("authority" in error.message for error in errors)


def test_receipt_schema_rejects_invalid_risk_class_and_approval_method():
    receipt = load_yaml(ROOT / "examples" / "claim-payout-receipt.yaml")
    receipt["risk_class"] = "urgent"
    receipt["authority"]["approval_method"] = "rubber_stamp"
    errors = list(Draft202012Validator(load_json(RECEIPT_SCHEMA)).iter_errors(receipt))
    messages = [error.message for error in errors]
    assert any("'urgent' is not one of" in message for message in messages)
    assert any("'rubber_stamp' is not one of" in message for message in messages)


def test_receipt_schema_rejects_null_decision_id():
    receipt = load_yaml(ROOT / "examples" / "claim-payout-receipt.yaml")
    receipt["decision_id"] = None
    errors = list(Draft202012Validator(load_json(RECEIPT_SCHEMA)).iter_errors(receipt))
    assert any("None is not of type 'string'" in error.message for error in errors)


def test_action_request_schema_rejects_invalid_risk_class():
    request = load_json(ROOT / "examples" / "verify-action-deploy.json")
    request["risk_class"] = "urgent"
    errors = list(Draft202012Validator(load_json(ACTION_SCHEMA)).iter_errors(request))
    assert any("'urgent' is not one of" in error.message for error in errors)
