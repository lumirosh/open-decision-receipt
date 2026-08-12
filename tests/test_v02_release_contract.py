import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from dam_verify.engine import BundleStore, ReceiptStore, approve, seal, verify_action, watch
from dam_verify.receipt import NEEDS_HUMAN_REVIEW, SEALED


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "cert_gated_deployment.yaml"


@pytest.fixture
def stores(tmp_path):
    bundles_dir = tmp_path / "bundles"
    bundles_dir.mkdir()
    (bundles_dir / FIXTURE.name).write_text(FIXTURE.read_text())
    return BundleStore(bundles_dir), ReceiptStore(tmp_path / "receipts"), bundles_dir / FIXTURE.name


def request():
    return {
        "workflow": "cert_gated_deployment",
        "actor": "release_workflow",
        "action": "deploy_certified_workflow",
        "risk_class": "high",
        "context_refs": ["certification_status"],
    }


def sealed(bundles):
    receipt = approve(verify_action(request(), bundles), approver="operator")
    return seal(receipt, {"executed_by": "workflow", "execution_result": "success"}, bundles)


def test_authority_only_drift_reopens_sealed_parent(stores):
    bundles, receipts, bundle_path = stores
    parent = sealed(bundles)
    receipts.save(parent)
    before = deepcopy(parent.to_dict())

    bundle = yaml.safe_load(bundle_path.read_text())
    bundle["authority_rules"][0]["basis"] = "runbook://cert-gated-deployment#revoked"
    bundle_path.write_text(yaml.safe_dump(bundle))

    children = watch(receipts, bundles)

    assert len(children) == 1
    assert receipts.load(parent.decision_id).to_dict() == before
    assert children[0].status == NEEDS_HUMAN_REVIEW
    event = receipts.events_for(parent.decision_id)[0]
    assert event["drift_types"] == ["authority"]
    assert event["previous_authority_hash"] != event["current_authority_hash"]


def test_authority_change_before_consequence_refuses_seal(stores):
    bundles, _, bundle_path = stores
    receipt = approve(verify_action(request(), bundles), approver="operator")
    bundle = yaml.safe_load(bundle_path.read_text())
    bundle["authority_rules"][0]["allowed_actions"] = []
    bundle_path.write_text(yaml.safe_dump(bundle))

    result = seal(receipt, {"executed_by": "workflow", "execution_result": "success"}, bundles)

    assert result.status == NEEDS_HUMAN_REVIEW
    assert any("authority changed" in item["finding"] for item in result.findings)


def test_successful_consequence_consumes_single_use_authority(stores):
    bundles, _, _ = stores
    receipt = sealed(bundles)

    assert receipt.status == SEALED
    assert receipt.authority["authorization_use"] == "single_use"
    assert receipt.authority["consumed_at"]
    assert receipt.authority["consumed_by_execution_hash"].startswith("sha256:")
    with pytest.raises(ValueError, match="consumed"):
        seal(receipt, {"executed_by": "workflow", "execution_result": "success"}, bundles)


def test_committed_end_to_end_artifacts_validate():
    directory = ROOT / "examples" / "end-to-end-artifact-bundle"
    receipt_schema = json.loads((ROOT / "schemas" / "decision-receipt.schema.json").read_text())
    event_schema = json.loads((ROOT / "schemas" / "reopen-event.schema.json").read_text())
    receipt_validator = Draft202012Validator(receipt_schema)
    event_validator = Draft202012Validator(event_schema)

    for name in ("allow-sealed-receipt.json", "refuse-receipt.json", "child-revalidation.json"):
        receipt_validator.validate(json.loads((directory / name).read_text()))
    event_validator.validate(json.loads((directory / "reopen-event.json").read_text()))


def test_expired_authority_cannot_authorize(stores):
    bundles, _, bundle_path = stores
    bundle = yaml.safe_load(bundle_path.read_text())
    bundle["authority_rules"][0]["expires_at"] = "2000-01-01T00:00:00+00:00"
    bundle_path.write_text(yaml.safe_dump(bundle))

    receipt = verify_action(request(), bundles)

    assert receipt.status == "denied"
    assert any("expired" in item["finding"] for item in receipt.findings)


def test_store_does_not_duplicate_second_identical_seal(stores):
    bundles, receipts, _ = stores
    first = approve(verify_action(request(), bundles), approver="operator")
    stale = deepcopy(first)
    receipts.save(seal(first, {"executed_by": "workflow", "execution_result": "success"}, bundles))

    second = seal(stale, {"executed_by": "workflow", "execution_result": "success"}, bundles)
    receipts.save(second)

    assert len(receipts.all()) == 1
    assert sum(1 for entry in receipts.chain._entries() if entry["decision_id"] == first.decision_id) == 1


def test_legacy_sealed_receipt_without_authority_hash_is_not_spuriously_reopened(stores):
    bundles, receipts, _ = stores
    parent = sealed(bundles)
    parent.check.pop("authority_hash_at_check")
    parent.check.pop("authority_snapshot")
    receipts.save(parent)

    assert watch(receipts, bundles) == []
