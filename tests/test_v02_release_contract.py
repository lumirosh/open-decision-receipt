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


def execution(receipt):
    return {
        "executed_by": "workflow",
        "execution_result": "success",
        "canonical_action": receipt.request["canonical_action"],
    }


def human_approve(receipt, bundles, approver="operator"):
    return approve(
        receipt,
        approver=approver,
        bundles=bundles,
        approver_role="change_authority",
    )


def sealed(bundles):
    receipt = human_approve(verify_action(request(), bundles), bundles)
    return seal(receipt, execution(receipt), bundles)


def test_authority_and_path_drift_reopen_sealed_parent(stores):
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
    assert event["drift_types"] == ["authority", "authority_path"]
    assert event["previous_authority_hash"] != event["current_authority_hash"]


def test_authority_change_before_consequence_refuses_seal(stores):
    bundles, _, bundle_path = stores
    receipt = human_approve(verify_action(request(), bundles), bundles)
    bundle = yaml.safe_load(bundle_path.read_text())
    bundle["authority_rules"][0]["allowed_actions"] = []
    bundle_path.write_text(yaml.safe_dump(bundle))

    result = seal(receipt, execution(receipt), bundles)

    assert result.status == NEEDS_HUMAN_REVIEW
    assert any("authority changed" in item["finding"] for item in result.findings)


def test_unbound_explicit_approval_fails_closed(stores):
    bundles, _, _ = stores
    receipt = human_approve(verify_action(request(), bundles), bundles)
    for field in (
        "approver_role",
        "approver_authority_snapshot",
        "approver_authority_hash",
        "approval_expires_at",
    ):
        receipt.authority.pop(field)

    result = seal(receipt, execution(receipt), bundles)

    assert result.status == NEEDS_HUMAN_REVIEW
    assert result.authority["consumed_at"]
    assert any("approval is unbound" in item["finding"] for item in result.findings)


def test_approver_must_hold_the_claimed_role(stores):
    bundles, _, _ = stores
    with pytest.raises(PermissionError, match="not authorized"):
        approve(
            verify_action(request(), bundles),
            approver="intruder",
            bundles=bundles,
            approver_role="change_authority",
        )


def test_expired_human_approval_refuses_seal(stores):
    bundles, _, _ = stores
    receipt = approve(
        verify_action(request(), bundles),
        approver="operator",
        bundles=bundles,
        approver_role="change_authority",
        approval_ttl_seconds=-1,
    )

    result = seal(receipt, execution(receipt), bundles)

    assert result.status == NEEDS_HUMAN_REVIEW
    assert result.authority["consumed_at"]
    assert any("approval expired" in item["finding"] for item in result.findings)


def test_malformed_approval_expiry_fails_closed(stores):
    bundles, _, _ = stores
    receipt = human_approve(verify_action(request(), bundles), bundles)
    receipt.authority["approval_expires_at"] = "not-a-timestamp"

    result = seal(receipt, execution(receipt), bundles)

    assert result.status == NEEDS_HUMAN_REVIEW
    assert result.authority["consumed_at"]
    assert any("approval expired" in item["finding"] for item in result.findings)


def test_revoked_approver_role_refuses_seal(stores):
    bundles, _, bundle_path = stores
    receipt = approve(
        verify_action(request(), bundles),
        approver="operator",
        bundles=bundles,
        approver_role="change_authority",
    )
    bundle = yaml.safe_load(bundle_path.read_text())
    bundle["human_gate"]["role_assignments"]["change_authority"] = []
    bundle_path.write_text(yaml.safe_dump(bundle))

    result = seal(receipt, execution(receipt), bundles)

    assert result.status == NEEDS_HUMAN_REVIEW
    assert result.authority["consumed_at"]
    assert any("approver authority changed" in item["finding"] for item in result.findings)


def test_failed_seal_consumes_authority_and_requires_reconciliation(stores):
    bundles, _, bundle_path = stores
    receipt = human_approve(verify_action(request(), bundles), bundles)
    bundle = yaml.safe_load(bundle_path.read_text())
    bundle["authority_rules"][0]["allowed_actions"] = []
    bundle_path.write_text(yaml.safe_dump(bundle))

    result = seal(receipt, execution(receipt), bundles)

    assert result.status == NEEDS_HUMAN_REVIEW
    assert result.authority["consumed_at"]
    assert result.execution["execution_attempted"] is True
    assert result.execution["reconciliation_required"] is True
    with pytest.raises(ValueError, match="consumed"):
        seal(result, execution(result), bundles)
    with pytest.raises(ValueError, match="consumed"):
        human_approve(result, bundles, approver="operator-2")


def test_malformed_execution_record_is_consumed_and_persistable(stores):
    bundles, receipts, _ = stores
    receipt = human_approve(verify_action(request(), bundles), bundles)

    result = seal(receipt, execution(receipt) | {"raw": {"not-json"}}, bundles)
    receipts.save(result)

    restored = receipts.load(result.decision_id)
    assert restored.status == NEEDS_HUMAN_REVIEW
    assert restored.authority["consumed_at"]
    assert restored.execution["execution_record_invalid"] == "TypeError"
    assert restored.execution["reconciliation_required"] is True


def test_successful_consequence_consumes_single_use_authority(stores):
    bundles, _, _ = stores
    receipt = sealed(bundles)

    assert receipt.status == SEALED
    assert receipt.authority["authorization_use"] == "single_use"
    assert receipt.authority["consumed_at"]
    assert receipt.authority["consumed_by_execution_hash"].startswith("sha256:")
    assert receipt.execution["outcome_state"] == "confirmed"
    assert receipt.execution["reconciliation_required"] is False
    with pytest.raises(ValueError, match="consumed"):
        seal(receipt, execution(receipt), bundles)


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
    first = human_approve(verify_action(request(), bundles), bundles)
    stale = deepcopy(first)
    receipts.save(seal(first, execution(first), bundles))

    second = seal(stale, execution(stale), bundles)
    receipts.save(second)

    assert len(receipts.all()) == 1
    assert sum(1 for entry in receipts.chain._entries() if entry["decision_id"] == first.decision_id) == 1


def test_legacy_sealed_receipt_without_authority_hash_is_not_spuriously_reopened(stores):
    bundles, receipts, _ = stores
    parent = sealed(bundles)
    parent.check.pop("authority_hash_at_check")
    parent.check.pop("authority_snapshot")
    parent.authority.pop("resolved_path", None)
    receipts.save(parent)

    assert watch(receipts, bundles) == []


def test_resolved_authority_path_is_deterministic_across_list_order(stores):
    bundles, _, bundle_path = stores
    first = verify_action(request(), bundles).authority["resolved_path"]

    bundle = yaml.safe_load(bundle_path.read_text())
    rule = bundle["authority_rules"][0]
    rule["actors"].reverse()
    rule["denied_actions"].reverse()
    bundle_path.write_text(yaml.safe_dump(bundle, sort_keys=False))

    second = verify_action(request(), bundles).authority["resolved_path"]

    assert first == second
    assert first["path_hash"].startswith("sha256:")
    assert first["dependency_ids"] == sorted(first["dependency_ids"])


def test_authority_path_only_drift_reopens_without_mutating_parent(stores):
    bundles, receipts, bundle_path = stores
    parent = sealed(bundles)
    receipts.save(parent)
    before = deepcopy(parent.to_dict())

    bundle = yaml.safe_load(bundle_path.read_text())
    bundle["authority_rules"][0]["required_evidence"].append("deployment_window")
    bundle["evidence_sources"]["deployment_window"] = {"version": 1, "content": "OPEN"}
    bundle_path.write_text(yaml.safe_dump(bundle, sort_keys=False))

    children = watch(receipts, bundles)

    assert len(children) == 1
    assert receipts.load(parent.decision_id).to_dict() == before
    event = receipts.events_for(parent.decision_id)[0]
    assert event["drift_types"] == ["authority_path"]
    assert event["previous_authority_path_hash"] != event["current_authority_path_hash"]
    assert "authority-rule:cert_gated_deployment:3" in event["changed_dependencies"]


def test_ambiguous_exact_authority_rules_fail_closed(stores):
    bundles, _, bundle_path = stores
    bundle = yaml.safe_load(bundle_path.read_text())
    bundle["authority_rules"].insert(1, deepcopy(bundle["authority_rules"][0]))
    bundle_path.write_text(yaml.safe_dump(bundle, sort_keys=False))

    receipt = verify_action(request(), bundles)

    assert receipt.status == "denied"
    assert any("ambiguous" in item["finding"] for item in receipt.findings)


def test_caller_context_cannot_replace_policy_required_evidence(stores):
    bundles, _, _ = stores
    req = request()
    req["context_refs"] = ["caller_supplied_extra"]

    receipt = verify_action(req, bundles)

    assert receipt.status == NEEDS_HUMAN_REVIEW
    assert receipt.check["evidence_refs"] == ["caller_supplied_extra", "certification_status"]
    assert receipt.check["missing"] == ["caller_supplied_extra"]
    assert "evidence:certification_status" in receipt.authority["resolved_path"]["dependency_ids"]


def test_authority_path_change_before_consequence_refuses_seal(stores):
    bundles, _, bundle_path = stores
    receipt = human_approve(verify_action(request(), bundles), bundles)
    bundle = yaml.safe_load(bundle_path.read_text())
    bundle["authority_rules"][0]["required_evidence"].append("deployment_window")
    bundle["evidence_sources"]["deployment_window"] = {"version": 1, "content": "OPEN"}
    bundle_path.write_text(yaml.safe_dump(bundle, sort_keys=False))

    result = seal(receipt, execution(receipt), bundles)

    assert result.status == NEEDS_HUMAN_REVIEW
    assert any("authority path changed" in item["finding"] for item in result.findings)


def test_missing_bundle_version_fails_closed_before_path_resolution(stores):
    bundles, _, bundle_path = stores
    bundle = yaml.safe_load(bundle_path.read_text())
    bundle.pop("version")
    bundle_path.write_text(yaml.safe_dump(bundle, sort_keys=False))

    receipt = verify_action(request(), bundles)

    assert receipt.status == "unknown"
    assert "resolved_path" not in receipt.authority
    assert any("version" in item["finding"] for item in receipt.findings)


def test_revoked_rule_never_claims_requester_authority(stores):
    bundles, _, bundle_path = stores
    bundle = yaml.safe_load(bundle_path.read_text())
    bundle["authority_rules"][0]["revoked"] = True
    bundle_path.write_text(yaml.safe_dump(bundle, sort_keys=False))

    receipt = verify_action(request(), bundles)

    assert receipt.status == "denied"
    assert receipt.request["requester_authority"] == "unresolved"


def test_changed_dependencies_include_previous_and_current_rule_ids(stores):
    bundles, receipts, bundle_path = stores
    parent = sealed(bundles)
    receipts.save(parent)
    bundle = yaml.safe_load(bundle_path.read_text())
    bundle["version"] = 4
    bundle_path.write_text(yaml.safe_dump(bundle, sort_keys=False))

    watch(receipts, bundles)

    event = receipts.events_for(parent.decision_id)[0]
    assert event["changed_dependencies"] == [
        "authority-rule:cert_gated_deployment:3",
        "authority-rule:cert_gated_deployment:4",
    ]
