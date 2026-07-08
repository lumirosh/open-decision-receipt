"""DAM verify-action engine - authorize, seal, watch.

The action path of DAM: the only new machinery on top of the existing
observe/lobby/verify/promote engines. Reference implementation on flat files;
Hermes grafts onto dam_rag / OKF store on the VPS.

Core invariants:
  1. No authority bundle -> UNKNOWN (never fail open).
  2. Action outside the actor's allowed set -> DENIED.
  3. Missing evidence -> NEEDS_HUMAN_REVIEW, never silently authorized.
  4. High-risk always crosses the human gate; approval writes scoped authority.
  5. seal() refuses to seal when the check-time and execution-time context
     hashes diverge: the receipt REOPENS instead. That is the TOCTOU catch.
  6. watch() reopens sealed receipts whose evidence basis changed after seal.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import yaml

from .receipt import (
    Receipt, now_iso, sha256_of,
    AUTHORIZED, DENIED, NEEDS_HUMAN_REVIEW, UNKNOWN, SEALED, REOPENED,
)


# ---------------------------------------------------------------- bundle store

class BundleStore:
    """OKF-style authority bundles on disk. One YAML per workflow.

    Bundle shape:
      workflow: cert_gated_deployment
      version: 3
      authority_rules:
        - actors: [ops_agent, release_workflow]
          risk_classes: [high]
          allowed_actions: [deploy_certified_workflow]
          denied_actions: [modify_certification, bypass_gate]
          requires_human: true
          basis: "runbook://cert-gated-deployment#v3"
      evidence_sources:
        certification_status: {version: 7, content: "cert VALID until ..."}
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def resolve(self, workflow: str) -> dict | None:
        path = self.root / f"{workflow}.yaml"
        if not path.exists():
            return None
        return yaml.safe_load(path.read_text())

    def evidence_for(self, workflow: str, refs: list[str]) -> tuple[dict, list[str]]:
        """Return ({ref: {version, content_hash}}, missing_refs)."""
        bundle = self.resolve(workflow) or {}
        sources = bundle.get("evidence_sources", {})
        found, missing = {}, []
        for ref in refs:
            src = sources.get(ref)
            if src is None:
                missing.append(ref)
            else:
                found[ref] = {
                    "version": src.get("version"),
                    "content_hash": sha256_of(src.get("content", "")),
                }
        return found, missing


def context_hash(evidence: dict) -> str:
    """Deliberately boring: hash of the evidence refs, versions, and content
    hashes the decision depends on. If any referenced source changes, the
    receipt's world has changed."""
    return sha256_of(evidence)


# ---------------------------------------------------------------- receipt store

class ReceiptStore:
    """Append-only evidence plane. Flat JSON files; VPS version is a table.

    Sealed receipts are appended to a tamper-evident hash chain.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        from .chain import ReceiptChain
        self.chain = ReceiptChain(self.root)

    def save(self, r: Receipt) -> Path:
        path = self.root / f"{r.decision_id}.json"
        path.write_text(json.dumps(r.to_dict(), indent=2))
        if r.status == SEALED and r.receipt.get("integrity_hash") and not self.chain.has(r.decision_id):
            self.chain.append(r.decision_id, r.receipt["integrity_hash"])
        return path

    def load(self, decision_id: str) -> Receipt:
        data = json.loads((self.root / f"{decision_id}.json").read_text())
        return Receipt(**data)

    def all(self) -> list[Receipt]:
        return [Receipt(**json.loads(p.read_text())) for p in sorted(self.root.glob("*.json"))]


# ---------------------------------------------------------------- core verbs

def verify_action(req: dict, bundles: BundleStore) -> Receipt:
    """The BEFORE tense. Returns a receipt in one of:
    authorized | denied | needs_human_review | unknown."""
    r = Receipt(
        decision_id=f"DR-{now_iso()[:10]}-{uuid.uuid4().hex[:6]}",
        workflow=req["workflow"],
        decision_type=req["action"],
        risk_class=req.get("risk_class", "high"),
        request={
            "requester": req["actor"],
            "requester_authority": req.get("actor_authority", "unresolved"),
            "requested_action": req["action"],
            "requested_at": now_iso(),
            "params": req.get("params", {}),
        },
    )

    # 1. Authority bundle must exist. Absence is UNKNOWN, never open.
    bundle = bundles.resolve(req["workflow"])
    if bundle is None:
        r.status = UNKNOWN
        r.flag(f"no authority bundle for workflow '{req['workflow']}' - fail closed")
        return r

    # 2. Find the rule governing this actor + risk class.
    rule = _match_rule(bundle, req)
    if rule is None:
        r.status = DENIED
        r.flag("no authority rule matches this actor/risk class - denied by default")
        return r

    r.request["requester_authority"] = rule.get("basis", "unspecified")
    r.boundary = {
        "allowed_actions": rule.get("allowed_actions", []),
        "denied_actions": rule.get("denied_actions", []),
        "failure_mode": "fail_closed",
    }

    # 3. Action must be inside the allowed set. Downstream structured-output
    # or runtime-control layers can consume this boundary.
    if req["action"] in r.boundary["denied_actions"] or \
       req["action"] not in r.boundary["allowed_actions"]:
        r.status = DENIED
        r.flag(f"action '{req['action']}' outside allowed set {r.boundary['allowed_actions']}")
        return r

    # 4. Evidence: attach and freeze check-time context.
    refs = req.get("context_refs", []) or rule.get("required_evidence", [])
    evidence, missing = bundles.evidence_for(req["workflow"], refs)
    r.check = {
        "checked_by": "dam.verify_action",
        "checked_at": now_iso(),
        "evidence_refs": refs,
        "evidence_seen": evidence,
        "context_hash_at_check": context_hash(evidence),
    }
    if missing:
        r.status = NEEDS_HUMAN_REVIEW
        r.check["missing"] = missing
        r.flag(f"missing evidence: {missing}")
        return r

    # 5. Human gate: high risk means a human signs authority into the object.
    if rule.get("requires_human", True):
        r.status = NEEDS_HUMAN_REVIEW
        r.flag("human approval required before authorization (by rule)")
        return r

    r.status = AUTHORIZED
    r.authority = {
        "approver": "policy",
        "approval_method": "policy",
        "approved_at": now_iso(),
        "authority_basis": rule.get("basis", "unspecified"),
        "approval_scope": req["action"],
        "separation_of_duties_ok": True,
    }
    return r


def approve(r: Receipt, approver: str, scope: str | None = None) -> Receipt:
    """The human signs. Presence becomes authorship."""
    if r.status != NEEDS_HUMAN_REVIEW:
        raise ValueError(f"cannot approve receipt in status '{r.status}'")
    if r.check.get("missing"):
        raise ValueError(f"cannot approve with missing evidence: {r.check['missing']}")
    r.authority = {
        "approver": approver,
        "approval_method": "explicit",
        "approved_at": now_iso(),
        "authority_basis": r.request.get("requester_authority", "unspecified"),
        "approval_scope": scope or r.request["requested_action"],
        "separation_of_duties_ok": approver != r.request["requester"],
    }
    if not r.authority["separation_of_duties_ok"]:
        r.flag("SoD violation: approver is the requester")
    r.status = AUTHORIZED
    return r


def seal(r: Receipt, execution_record: dict, bundles: BundleStore) -> Receipt:
    """The AFTER tense - but only if the world held still.
    Hash divergence between check and execution = TOCTOU: refuse to seal."""
    if r.status != AUTHORIZED:
        raise ValueError(f"cannot seal receipt in status '{r.status}'")

    evidence_now, missing = bundles.evidence_for(r.workflow, r.check.get("evidence_refs", []))
    ctx_now = context_hash(evidence_now)

    r.execution = dict(execution_record) | {
        "executed_at": now_iso(),
        "context_hash_at_execution": ctx_now,
    }

    if missing or ctx_now != r.check.get("context_hash_at_check"):
        r.status = REOPENED
        r.flag("TOCTOU: context changed between check and use - sealing refused, re-verification required")
        return r

    r.status = SEALED
    r.receipt = {
        "replayable": True,
        "integrity_hash": r.seal_hash(),
        "sealed_at": now_iso(),
    }
    return r


def watch(store: ReceiptStore, bundles: BundleStore) -> list[Receipt]:
    """The OVER-TIME tense. Sealed proof becomes a question again when its
    evidence basis drifts. Returns the receipts reopened in this pass."""
    reopened = []
    for r in store.all():
        if r.status != SEALED:
            continue
        evidence_now, missing = bundles.evidence_for(r.workflow, r.check.get("evidence_refs", []))
        if missing or context_hash(evidence_now) != r.check.get("context_hash_at_check"):
            r.status = REOPENED
            r.flag("basis drift detected by watcher - receipt reopened, authority requires re-verification")
            store.save(r)
            reopened.append(r)
    return reopened


def _match_rule(bundle: dict, req: dict) -> dict | None:
    for rule in bundle.get("authority_rules", []):
        if req["actor"] in rule.get("actors", []) and \
           req.get("risk_class", "high") in rule.get("risk_classes", []):
            return rule
    return None
