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
