"""Tests for chain, grammar, and replay extensions."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for module_name in list(sys.modules):
    if module_name == "dam_verify" or module_name.startswith("dam_verify."):
        del sys.modules[module_name]

from dam_verify.cli import replay
from dam_verify.engine import BundleStore, ReceiptStore, approve, seal, verify_action
from dam_verify.grammar import compile_action_schema
from dam_verify.receipt import AUTHORIZED, NEEDS_HUMAN_REVIEW

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


def sealed_receipt(bundle_store, deploy_request):
    receipt = approve(verify_action(deploy_request, bundle_store), approver="operator", bundles=bundle_store, approver_role="change_authority")
    return seal(receipt, {"executed_by": "workflow", "execution_result": "success", "canonical_action": receipt.request["canonical_action"]}, bundle_store)


def test_sealed_receipts_enter_tamper_evident_chain(bundle_store, receipt_store, deploy_request):
    receipt = sealed_receipt(bundle_store, deploy_request)
    receipt_store.save(receipt)

    assert receipt_store.chain.has(receipt.decision_id)
    ok, broken = receipt_store.chain.verify()
    assert ok and broken is None


def test_chain_detects_tampering(bundle_store, receipt_store, deploy_request):
    for _ in range(3):
        receipt_store.save(sealed_receipt(bundle_store, deploy_request))

    lines = receipt_store.chain.path.read_text().splitlines()
    entry = json.loads(lines[1])
    entry["integrity_hash"] = "sha256:forged"
    lines[1] = json.dumps(entry)
    receipt_store.chain.path.write_text("\n".join(lines) + "\n")

    ok, broken = receipt_store.chain.verify()
    assert not ok and broken == 1


def test_chain_detects_receipt_body_tampering(bundle_store, receipt_store, deploy_request):
    receipt = sealed_receipt(bundle_store, deploy_request)
    path = receipt_store.save(receipt)
    body = json.loads(path.read_text())
    body["execution"]["execution_result"] = "tampered"
    path.write_text(json.dumps(body))

    ok, broken = receipt_store.chain.verify()

    assert not ok and broken == 0


def test_sealed_receipt_cannot_be_overwritten_as_unsealed(bundle_store, receipt_store, deploy_request):
    receipt = sealed_receipt(bundle_store, deploy_request)
    receipt_store.save(receipt)
    receipt.status = AUTHORIZED

    with pytest.raises(ValueError, match="already sealed"):
        receipt_store.save(receipt)


def test_resave_does_not_double_append_chain(bundle_store, receipt_store, deploy_request):
    receipt = sealed_receipt(bundle_store, deploy_request)
    receipt_store.save(receipt)
    receipt_store.save(receipt)

    assert sum(1 for entry in receipt_store.chain._entries() if entry["decision_id"] == receipt.decision_id) == 1


def test_action_parameter_mutation_refuses_seal(bundle_store, deploy_request):
    receipt = approve(verify_action(deploy_request, bundle_store), approver="operator", bundles=bundle_store, approver_role="change_authority")
    assert receipt.authority["action_hash"] == receipt.request["action_hash"]

    result = seal(receipt, {
        "executed_by": "workflow",
        "execution_result": "success",
        "canonical_action": {
            "workflow": deploy_request["workflow"],
            "action_type": deploy_request["action"],
            "parameters": {"environment": "production", "path": "B"},
        },
    }, bundle_store)

    assert result.status == NEEDS_HUMAN_REVIEW
    assert any("action commitment changed" in item["finding"] for item in result.findings)


def test_missing_action_commitment_fails_closed(bundle_store, deploy_request):
    receipt = approve(verify_action(deploy_request, bundle_store), approver="operator", bundles=bundle_store, approver_role="change_authority")
    receipt.request.pop("action_hash")
    receipt.authority.pop("action_hash")

    result = seal(receipt, {"executed_by": "workflow", "execution_result": "success"}, bundle_store)

    assert result.status == NEEDS_HUMAN_REVIEW
    assert any("action commitment" in item["finding"] for item in result.findings)


def test_grammar_requires_authority(bundle_store, deploy_request):
    receipt = verify_action(deploy_request, bundle_store)
    assert receipt.status == NEEDS_HUMAN_REVIEW

    with pytest.raises(ValueError):
        compile_action_schema(receipt)


def test_grammar_scopes_to_authorized_receipt(bundle_store, deploy_request):
    receipt = approve(verify_action(deploy_request, bundle_store), approver="operator", bundles=bundle_store, approver_role="change_authority")
    schema = compile_action_schema(receipt)

    assert schema["properties"]["action"]["enum"] == ["deploy_certified_workflow"]
    assert schema["properties"]["decision_id"]["const"] == receipt.decision_id
    assert "bypass_gate" not in schema["properties"]["action"]["enum"]


def test_grammar_can_render_from_sealed_receipt_for_replay(bundle_store, deploy_request):
    receipt = sealed_receipt(bundle_store, deploy_request)
    schema = compile_action_schema(receipt)

    assert schema["properties"]["decision_id"]["const"] == receipt.decision_id


def test_replay_tells_decision_story(bundle_store, deploy_request):
    receipt = sealed_receipt(bundle_store, deploy_request)
    output = replay(receipt)

    assert "SEALED" in output
    assert "operator" in output
    assert "check==use : True" in output
