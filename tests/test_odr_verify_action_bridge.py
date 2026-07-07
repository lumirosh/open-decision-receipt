"""Integration tests for DAM verify-action bridge.

These tests lock the cert-drift demo contract: same action can seal while the
authority basis is valid, then reopen/fail closed when that basis drifts.
"""

import copy
import json
from pathlib import Path

import pytest
import yaml

from dam_verify.engine import BundleStore, ReceiptStore, approve, seal, verify_action, watch
from dam_verify.receipt import NEEDS_HUMAN_REVIEW, REOPENED, SEALED


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


def test_cert_drift_story_same_action_allowed_then_reopened(bundle_store, receipt_store, deploy_request):
    receipt = verify_action(deploy_request, bundle_store)
    assert receipt.status == NEEDS_HUMAN_REVIEW

    receipt = approve(receipt, approver="operator")
    receipt = seal(receipt, {"executed_by": "workflow", "execution_result": "success"}, bundle_store)
    assert receipt.status == SEALED
    assert receipt.replayable
    receipt_store.save(receipt)

    revoke_cert(bundle_store)

    reopened = watch(receipt_store, bundle_store)
    assert [r.decision_id for r in reopened] == [receipt.decision_id]
    assert receipt_store.load(receipt.decision_id).status == REOPENED


def test_seal_refuses_to_seal_if_basis_changes_between_check_and_use(bundle_store, deploy_request):
    receipt = approve(verify_action(deploy_request, bundle_store), approver="operator")
    revoke_cert(bundle_store)

    receipt = seal(receipt, {"executed_by": "workflow", "execution_result": "success"}, bundle_store)

    assert receipt.status == REOPENED
    assert any("TOCTOU" in finding["finding"] for finding in receipt.findings)


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
