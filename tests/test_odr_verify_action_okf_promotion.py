"""Tests for promoting verified action receipts into OKF bundles."""

import json
from pathlib import Path

from dam_verify.engine import BundleStore, ReceiptStore, approve, seal, verify_action
from dam_verify.receipt import SEALED
from dam_verify.okf import promote_receipt_bundle


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cert_gated_deployment.yaml"


def sealed_receipt(tmp_path):
    bundle_dir = tmp_path / "bundles"
    bundle_dir.mkdir()
    (bundle_dir / "cert_gated_deployment.yaml").write_text(FIXTURE.read_text())
    bundles = BundleStore(bundle_dir)
    req = {
        "actor": "release_workflow",
        "workflow": "cert_gated_deployment",
        "action": "deploy_certified_workflow",
        "risk_class": "high",
        "context_refs": ["certification_status"],
    }
    receipt = approve(verify_action(req, bundles), approver="operator")
    receipt = seal(receipt, {"executed_by": "workflow", "execution_result": "success"}, bundles)
    assert receipt.status == SEALED
    ReceiptStore(tmp_path / "receipts").save(receipt)
    return receipt


def test_receipt_bundle_dry_run_preserves_human_gate(tmp_path):
    receipt = sealed_receipt(tmp_path)
    out = promote_receipt_bundle(receipt, tmp_path / "okf", approve=False)

    assert out["approved"] is False
    assert not Path(out["path"]).exists()
    assert "user: pending" in out["content"]
    assert "dam: verified" in out["content"]
    assert "Receipt status: sealed" in out["content"]
    assert receipt.decision_id in out["content"]


def test_receipt_bundle_approve_writes_verified_okf_bundle(tmp_path):
    receipt = sealed_receipt(tmp_path)
    out = promote_receipt_bundle(receipt, tmp_path / "okf", approve=True)

    path = Path(out["path"])
    assert out["approved"] is True
    assert path.exists()
    content = path.read_text()
    assert "type: decision" in content
    assert "state: verified" in content
    assert "user: approved" in content
    assert "authority_boundary:" in content
