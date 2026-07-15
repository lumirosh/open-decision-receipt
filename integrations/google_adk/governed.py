"""Shared governed boundary used by the optional Google ADK examples."""
from __future__ import annotations

import json
import re
import secrets
from pathlib import Path
from typing import Any

import yaml

from dam_verify.engine import BundleStore, ReceiptStore, approve, seal, verify_action
from dam_verify.okf import promote_receipt_bundle
from dam_verify.receipt import DENIED, ESCALATED, NEEDS_HUMAN_REVIEW, now_iso


DECISION_ID_PATTERN = re.compile(r"DR-\d{4}-\d{2}-\d{2}-[0-9a-f]{6}")


class CasePackStore(BundleStore):
    def __init__(self, case_pack: str | Path):
        self.case_pack = Path(case_pack)
        super().__init__(self.case_pack.parent)

    def resolve(self, workflow: str) -> dict | None:
        if not self.case_pack.exists():
            return None
        pack = yaml.safe_load(self.case_pack.read_text()) or {}
        return pack if pack.get("workflow") == workflow else None


def _load_pack(path: str | Path) -> dict:
    pack = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(pack, dict):
        raise ValueError("case pack must be a mapping")
    return pack


def prepare_action(*, request: dict[str, Any], case_pack: str | Path, receipts_dir: str | Path) -> dict:
    pack = _load_pack(case_pack)
    store = ReceiptStore(Path(receipts_dir))
    receipt = verify_action(request, CasePackStore(case_pack))
    params = request.get("params") or {}
    receipt.recommendation = {
        "recommended_by": request["actor"],
        "recommendation": params.get("recommendation"),
        "confidence": params.get("confidence"),
        "rationale": params.get("rationale"),
    }
    receipt.accountability = dict(pack.get("accountability") or {})
    gate_token = secrets.token_urlsafe(24)
    receipt.boundary["human_gate_token"] = gate_token
    path = store.save(receipt)
    gate = pack.get("human_gate") or {}
    return {
        "decision_id": receipt.decision_id,
        "gate_token": gate_token,
        "status": receipt.status,
        "receipt_path": str(path.resolve()),
        "review_packet": {
            "subject_ref": params.get("subject_ref"),
            "recommendation": receipt.recommendation,
            "missing_evidence": receipt.check.get("missing", []),
            "allowed_decisions": gate.get("decisions", []),
            "allowed_approver_roles": gate.get("allowed_roles", []),
            "boundary": receipt.boundary,
            "reference_only": pack.get("reference_only", {}),
        },
    }


def decide_action(
    *, decision_id: str, gate_token: str, decision: str, approver: str, approver_role: str,
    note: str, case_pack: str | Path, receipts_dir: str | Path,
    actions_dir: str | Path, okf_bundles_dir: str | Path,
) -> dict:
    if DECISION_ID_PATTERN.fullmatch(decision_id) is None:
        raise ValueError("invalid decision_id")
    if not note.strip():
        raise ValueError("a human decision note is required")
    pack = _load_pack(case_pack)
    gate = pack.get("human_gate") or {}
    if decision not in gate.get("decisions", []):
        raise ValueError(f"unsupported decision {decision!r}")
    if approver_role not in gate.get("allowed_roles", []):
        raise PermissionError(f"role {approver_role!r} is not allowed for this workflow")

    store = ReceiptStore(Path(receipts_dir))
    receipt = store.load(decision_id)
    if receipt.workflow != pack.get("workflow"):
        raise ValueError(
            f"receipt {decision_id!r} does not belong to workflow {pack.get('workflow')!r}"
        )
    expected_gate_token = receipt.boundary.get("human_gate_token", "")
    if not expected_gate_token or not secrets.compare_digest(gate_token, expected_gate_token):
        raise ValueError("gate token does not match the displayed review")
    if receipt.status != NEEDS_HUMAN_REVIEW:
        raise ValueError(f"receipt is not waiting for human review: {receipt.status}")
    if receipt.check.get("missing") and decision == "approve":
        raise ValueError(f"cannot approve with missing evidence: {receipt.check['missing']}")

    authority = {
        "approver": approver,
        "approver_role": approver_role,
        "approval_method": "explicit",
        "authority_basis": receipt.request.get("requester_authority", "unspecified"),
        "reviewer_justification": note,
        "decided_at": now_iso(),
    }
    if decision != "approve":
        receipt.status = DENIED if decision == "reject" else ESCALATED if decision == "escalate" else NEEDS_HUMAN_REVIEW
        receipt.authority = authority | {
            "reviewer_decision": "rejected" if decision == "reject" else decision,
            "approval_scope": "none",
            "separation_of_duties_ok": approver != receipt.request.get("requester"),
        }
        receipt.flag(f"human decision: {decision}; no action executed")
        path = store.save(receipt)
        return {"decision_id": decision_id, "status": receipt.status, "receipt_path": str(path.resolve()), "external_action_performed": False}

    receipt = approve(receipt, approver=approver, scope=receipt.decision_type)
    receipt.authority.update(authority | {"reviewer_decision": "approved"})
    actions = Path(actions_dir)
    actions.mkdir(parents=True, exist_ok=True)
    artifact_path = actions / f"{decision_id}.json"
    artifact_path.write_text(json.dumps({
        "decision_id": decision_id,
        "subject_ref": receipt.request.get("params", {}).get("subject_ref"),
        "action": receipt.decision_type,
        "mode": "synthetic_local_only",
        "external_action_performed": False,
    }, indent=2, sort_keys=True) + "\n")
    receipt = seal(receipt, {
        "executed_by": "google_adk_reference",
        "tool_or_system": "local_json_artifact",
        "actual_action": receipt.decision_type,
        "execution_result": "synthetic_success",
        "external_action_performed": False,
        "artifact_path": str(artifact_path.resolve()),
    }, CasePackStore(case_pack))
    path = store.save(receipt)
    if receipt.status != "sealed":
        return {"decision_id": decision_id, "status": receipt.status, "receipt_path": str(path.resolve()), "external_action_performed": False}

    promotion = promote_receipt_bundle(receipt, okf_bundles_dir, approve=False)
    return {
        "decision_id": decision_id, "status": receipt.status,
        "receipt_path": str(path.resolve()),
        "action_artifact_path": str(artifact_path.resolve()),
        "external_action_performed": False,
        "okf_promotion": {"approved": promotion["approved"], "path": promotion["path"]},
    }
