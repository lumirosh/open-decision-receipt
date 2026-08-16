"""Integration tests for DAM verify-action bridge.

These tests lock the cert-drift demo contract: same action can seal while the
authority basis is valid, then create an append-only reopen event and linked
child lifecycle when that basis drifts.
"""

import copy
import json
from pathlib import Path

import pytest
import yaml

from dam_verify.engine import BundleStore, ReceiptStore, approve, seal, verify_action, watch
from dam_verify.receipt import NEEDS_HUMAN_REVIEW, SEALED


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cert_gated_deployment.yaml"


@pytest.fixture
def bundle_store(tmp_path):
    bundle_dir = tmp_path / "bundles"
    bundle_dir.mkdir()
    (bundle_dir / "cert_gated_deployment.yaml").write_text(FIXTURE.read_text())
    return BundleStore(bundle_dir)


@pytest.fixture
def receipt_store(tmp_path):
    return ReceiptStore(tmp_path / "receipts")


@pytest.fixture
def deploy_request():
    return {
        "actor": "release_workflow",
        "workflow": "cert_gated_deployment",
        "action": "deploy_certified_workflow",
        "risk_class": "high",
        "context_refs": ["certification_status"],
        "params": {"environment": "production", "path": "A"},
    }


def revoke_cert(bundle_store):
    path = bundle_store.root / "cert_gated_deployment.yaml"
    data = yaml.safe_load(path.read_text())
    data["evidence_sources"]["certification_status"]["version"] += 1
    data["evidence_sources"]["certification_status"]["content"] = (
        "Certification CERT-2214 REVOKED 2026-07-08. Scope invalidated."
    )
    path.write_text(yaml.safe_dump(data))


def test_cert_drift_preserves_sealed_parent_and_creates_linked_child(bundle_store, receipt_store, deploy_request):
    receipt = verify_action(deploy_request, bundle_store)
    assert receipt.status == NEEDS_HUMAN_REVIEW

    receipt = approve(receipt, approver="operator")
    receipt = seal(receipt, {"executed_by": "workflow", "execution_result": "success", "canonical_action": receipt.request["canonical_action"]}, bundle_store)
    assert receipt.status == SEALED
    assert receipt.replayable
    receipt_store.save(receipt)

    revoke_cert(bundle_store)

    children = watch(receipt_store, bundle_store)

    assert len(children) == 1
    child = children[0]
    assert child.parent_receipt_id == receipt.decision_id
    assert child.status == NEEDS_HUMAN_REVIEW
    assert receipt_store.load(receipt.decision_id).to_dict() == receipt.to_dict()
    events = receipt_store.events_for(receipt.decision_id)
    assert len(events) == 1
    assert events[0]["parent_receipt_id"] == receipt.decision_id
    assert events[0]["child_decision_id"] == child.decision_id

    assert watch(receipt_store, bundle_store) == []
    assert len(receipt_store.events_for(receipt.decision_id)) == 1


def test_seal_refuses_to_seal_if_basis_changes_between_check_and_use(bundle_store, deploy_request):
    receipt = approve(verify_action(deploy_request, bundle_store), approver="operator")
    revoke_cert(bundle_store)

    receipt = seal(receipt, {"executed_by": "workflow", "execution_result": "success", "canonical_action": receipt.request["canonical_action"]}, bundle_store)

    assert receipt.status == NEEDS_HUMAN_REVIEW
    assert any("TOCTOU" in finding["finding"] for finding in receipt.findings)


def test_policy_authorized_containment_seals_then_creates_child_when_intel_is_retracted(tmp_path):
    fixture = Path(__file__).resolve().parent / "fixtures" / "soc_automated_containment.yaml"
    bundle_dir = tmp_path / "bundles"
    bundle_dir.mkdir()
    (bundle_dir / "soc_automated_containment.yaml").write_text(fixture.read_text())
    bundles = BundleStore(bundle_dir)
    receipts = ReceiptStore(tmp_path / "receipts")
    request = {
        "actor": "containment_agent_v2",
        "workflow": "soc_automated_containment",
        "action": "isolate_host",
        "risk_class": "high",
        "context_refs": [
            "threat_intel_indicator",
            "login_anomaly_score",
            "asset_criticality",
        ],
        "params": {"host": "HOST-7734"},
    }

    receipt = verify_action(request, bundles)
    assert receipt.status == "authorized"
    assert receipt.authority["approval_method"] == "policy"
    assert receipt.boundary["failure_mode"] == "fail_closed"

    receipt = seal(receipt, {"executed_by": "containment_agent_v2", "execution_result": "success", "canonical_action": receipt.request["canonical_action"]}, bundles)
    assert receipt.status == SEALED
    receipts.save(receipt)

    path = bundle_dir / "soc_automated_containment.yaml"
    bundle = yaml.safe_load(path.read_text())
    bundle["evidence_sources"]["threat_intel_indicator"]["version"] += 1
    bundle["evidence_sources"]["threat_intel_indicator"]["content"] = "TI-88213 RETRACTED: false positive signature collision."
    path.write_text(yaml.safe_dump(bundle))

    children = watch(receipts, bundles)
    assert len(children) == 1
    assert children[0].parent_receipt_id == receipt.decision_id
    assert receipts.load(receipt.decision_id).status == SEALED
    assert "evidence drift" in receipts.events_for(receipt.decision_id)[0]["reason"]


def test_cli_verify_action_lifecycle_uses_configurable_paths(tmp_path, bundle_store, monkeypatch, deploy_request, capsys):
    import dam_verify.cli as cli

    action_file = tmp_path / "deploy-action.json"
    action_file.write_text(json.dumps(deploy_request))
    receipts_dir = tmp_path / "receipts"

    rc = cli.main([
        "--bundles-dir", str(bundle_store.root),
        "--receipts-dir", str(receipts_dir),
        "verify", str(action_file),
    ])
    assert rc == 0
    verify_out = json.loads(capsys.readouterr().out)
    assert verify_out["status"] == NEEDS_HUMAN_REVIEW

    decision_id = verify_out["decision_id"]
    rc = cli.main([
        "--bundles-dir", str(bundle_store.root),
        "--receipts-dir", str(receipts_dir),
        "approve", decision_id, "--approver", "operator",
    ])
    assert rc == 0
    approve_out = json.loads(capsys.readouterr().out)
    assert approve_out["status"] == "authorized"

    rc = cli.main([
        "--bundles-dir", str(bundle_store.root),
        "--receipts-dir", str(receipts_dir),
        "seal", decision_id,
    ])
    assert rc == 0
    seal_out = json.loads(capsys.readouterr().out)
    assert seal_out["status"] == SEALED

    revoke_cert(bundle_store)
    rc = cli.main([
        "--bundles-dir", str(bundle_store.root),
        "--receipts-dir", str(receipts_dir),
        "watch",
    ])
    assert rc == 0
    watch_out = capsys.readouterr().out
    assert "reopen_events: 1" in watch_out
    assert f"parent={decision_id}" in watch_out
    assert ReceiptStore(receipts_dir).load(decision_id).status == SEALED
