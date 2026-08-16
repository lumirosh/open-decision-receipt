"""DAM verify-action engine - authorize, seal, watch.

The action path of DAM: the only new machinery on top of the existing
observe/lobby/verify/promote engines. Reference implementation on flat files;
Hermes grafts onto dam_rag / OKF store on the VPS.

Core invariants:
  1. No authority bundle -> UNKNOWN (never fail open).
  2. Action outside the actor's allowed set -> DENIED.
  3. Missing evidence -> NEEDS_HUMAN_REVIEW, never silently authorized.
  4. High-risk crosses the human gate unless a versioned authority bundle
     explicitly pre-authorizes a narrow action surface; policy exceptions stay
     bounded and are still replayable and watchable.
  5. seal() refuses to seal when check-time and execution-time context hashes
     diverge and routes the attempt back to human review.
  6. watch() preserves sealed receipts, appends a ReopenEvent, and starts a
     linked child lifecycle when their evidence basis changes.
"""
from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .receipt import (
    Receipt, now_iso, sha256_of,
    AUTHORIZED, DENIED, NEEDS_HUMAN_REVIEW, UNKNOWN, SEALED,
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


def canonical_action(workflow: str, action: str, params: dict | None = None) -> dict:
    """Return the exact consequential object shared by request and execution."""
    return {
        "workflow": workflow,
        "action_type": action,
        "parameters": copy.deepcopy(params or {}),
    }


def approver_authority_snapshot(
    bundle: dict | None, approver: str, approver_role: str
) -> dict | None:
    if not bundle:
        return None
    gate = bundle.get("human_gate") or {}
    allowed_roles = sorted(gate.get("allowed_roles") or [])
    assigned_approvers = sorted((gate.get("role_assignments") or {}).get(approver_role) or [])
    if approver_role not in allowed_roles or approver not in assigned_approvers:
        return None
    return {
        "bundle": bundle.get("workflow"),
        "bundle_version": bundle.get("version"),
        "approver": approver,
        "approver_role": approver_role,
        "allowed_roles": allowed_roles,
        "assigned_approvers": assigned_approvers,
    }


def context_hash(evidence: dict) -> str:
    """Deliberately boring: hash of the evidence refs, versions, and content
    hashes the decision depends on. If any referenced source changes, the
    receipt's world has changed."""
    return sha256_of(evidence)


def _exact_rules(bundle: dict, req: dict) -> list[dict]:
    return [
        rule for rule in bundle.get("authority_rules", [])
        if req["actor"] in rule.get("actors", [])
        and req.get("risk_class", "high") in rule.get("risk_classes", [])
        and req["action"] in rule.get("allowed_actions", [])
        and req["action"] not in rule.get("denied_actions", [])
        and not rule.get("revoked", False)
        and not _expired(rule)
    ]


def authority_snapshot(bundle: dict | None, req: dict) -> dict | None:
    """Return the exact rule state relied on for this bounded action."""
    if bundle is None:
        return None
    if req.get("action"):
        rules = _exact_rules(bundle, req)
        rule = rules[0] if len(rules) == 1 else None
    else:
        rule = _match_rule(bundle, req)
    if rule is None:
        return None
    return {
        "bundle_version": bundle.get("version"),
        "actors": rule.get("actors", []),
        "risk_classes": rule.get("risk_classes", []),
        "allowed_actions": rule.get("allowed_actions", []),
        "denied_actions": rule.get("denied_actions", []),
        "requires_human": rule.get("requires_human", True),
        "basis": rule.get("basis"),
        "expires_at": rule.get("expires_at"),
        "revoked": rule.get("revoked", False),
    }


def authority_hash(bundle: dict | None, req: dict) -> str | None:
    snapshot = authority_snapshot(bundle, req)
    if snapshot is None or snapshot.get("revoked") or _expired(snapshot):
        return None
    return sha256_of(snapshot)


def resolved_authority_path(bundle: dict | None, req: dict) -> dict | None:
    """Resolve one deterministic authority path for the exact action."""
    if bundle is None or bundle.get("version") is None:
        return None
    matches = _exact_rules(bundle, req)
    if len(matches) != 1:
        return None
    rule = matches[0]
    workflow = bundle.get("workflow", req["workflow"])
    version = bundle.get("version")
    basis = rule.get("basis", "unspecified")
    evidence_refs = sorted(set(req.get("context_refs", [])) | set(rule.get("required_evidence", [])))
    edges = [
        {"subject": f"actor:{req['actor']}", "relationship": "may_execute", "object": f"action:{req['action']}"},
        {"subject": f"action:{req['action']}", "relationship": "governed_by", "object": f"policy:{basis}"},
        *(
            {"subject": f"action:{req['action']}", "relationship": "requires", "object": f"evidence:{ref}"}
            for ref in evidence_refs
        ),
    ]
    path = {
        "resolver_version": "1",
        "bundle": workflow,
        "bundle_version": version,
        "actor": req["actor"],
        "risk_class": req.get("risk_class", "high"),
        "action": req["action"],
        "requires_human": rule.get("requires_human", True),
        "expires_at": rule.get("expires_at"),
        "edges": sorted(edges, key=lambda edge: (edge["subject"], edge["relationship"], edge["object"])),
        "dependency_ids": sorted([
            f"authority-rule:{workflow}:{version}",
            *(f"evidence:{ref}" for ref in evidence_refs),
        ]),
    }
    return path | {"path_hash": sha256_of(path)}


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
        if path.exists():
            existing = Receipt(**json.loads(path.read_text()))
            if existing.status == SEALED and existing.to_dict() != r.to_dict():
                raise ValueError(f"authorization '{r.decision_id}' already sealed")
        path.write_text(json.dumps(r.to_dict(), indent=2))
        if r.status == SEALED and r.receipt.get("integrity_hash") and not self.chain.has(r.decision_id):
            self.chain.append(r.decision_id, r.receipt["integrity_hash"])
        return path

    def load(self, decision_id: str) -> Receipt:
        data = json.loads((self.root / f"{decision_id}.json").read_text())
        return Receipt(**data)

    def all(self) -> list[Receipt]:
        return [Receipt(**json.loads(p.read_text())) for p in sorted(self.root.glob("*.json"))]

    def save_event(self, event: dict) -> Path:
        path = self.root / "events" / f"{event['event_id']}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(event, indent=2))
        return path

    def events_for(self, parent_receipt_id: str) -> list[dict]:
        event_dir = self.root / "events"
        if not event_dir.exists():
            return []
        return [
            event for path in sorted(event_dir.glob("*.json"))
            if (event := json.loads(path.read_text())).get("parent_receipt_id") == parent_receipt_id
        ]


# ---------------------------------------------------------------- core verbs

def verify_action(req: dict, bundles: BundleStore) -> Receipt:
    """The BEFORE tense. Returns a receipt in one of:
    authorized | denied | needs_human_review | unknown."""
    requested_action = canonical_action(req["workflow"], req["action"], req.get("params"))
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
            "canonical_action": requested_action,
            "action_hash": sha256_of(requested_action),
        },
    )

    # 1. Authority bundle must exist. Absence is UNKNOWN, never open.
    bundle = bundles.resolve(req["workflow"])
    if bundle is None:
        r.status = UNKNOWN
        r.flag(f"no authority bundle for workflow '{req['workflow']}' - fail closed")
        return r
    if bundle.get("version") is None:
        r.status = UNKNOWN
        r.flag("authority bundle has no version - fail closed")
        return r

    # 2. Find the rule governing this actor + risk class.
    applicable_rules = [
        rule for rule in bundle.get("authority_rules", [])
        if req["actor"] in rule.get("actors", [])
        and req.get("risk_class", "high") in rule.get("risk_classes", [])
    ]
    exact_rules = _exact_rules(bundle, req)
    if len(exact_rules) > 1:
        r.status = DENIED
        r.flag("ambiguous authority: multiple rules permit this exact actor/risk/action - fail closed")
        return r
    rule = exact_rules[0] if exact_rules else (applicable_rules[0] if applicable_rules else None)
    if rule is None:
        r.status = DENIED
        r.flag("no authority rule matches this actor/risk class - denied by default")
        return r
    if rule.get("revoked", False):
        r.status = DENIED
        r.flag("authority rule revoked - denied")
        return r
    if _expired(rule):
        r.status = DENIED
        r.flag("authority rule expired - denied")
        return r

    r.request["requester_authority"] = rule.get("basis", "unspecified")
    r.check["authority_snapshot"] = authority_snapshot(bundle, req)
    r.check["authority_hash_at_check"] = authority_hash(bundle, req)
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
    refs = sorted(set(req.get("context_refs", [])) | set(rule.get("required_evidence", [])))
    path = resolved_authority_path(bundle, req | {"context_refs": refs})
    if path:
        r.authority["resolved_path"] = path
    evidence, missing = bundles.evidence_for(req["workflow"], refs)
    r.check |= {
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

    # 5. Human gate: default for high-risk. A bundle can pre-authorize only
    # a deliberately bounded policy action by setting requires_human: false.
    if rule.get("requires_human", True):
        r.status = NEEDS_HUMAN_REVIEW
        r.flag("human approval required before authorization (by rule)")
        return r

    r.status = AUTHORIZED
    r.authority |= {
        "approver": "policy",
        "approval_method": "policy",
        "approved_at": now_iso(),
        "authority_basis": rule.get("basis", "unspecified"),
        "approval_scope": req["action"],
        "action_hash": r.request["action_hash"],
        "separation_of_duties_ok": True,
        "authorization_use": "single_use",
        "consumed_at": None,
        "consumed_by_execution_hash": None,
    }
    return r


def approve(
    r: Receipt,
    approver: str,
    bundles: BundleStore,
    approver_role: str,
    scope: str | None = None,
    approval_ttl_seconds: int = 300,
) -> Receipt:
    """The human signs. Presence becomes authorship."""
    if r.status != NEEDS_HUMAN_REVIEW:
        raise ValueError(f"cannot approve receipt in status '{r.status}'")
    if r.check.get("missing"):
        raise ValueError(f"cannot approve with missing evidence: {r.check['missing']}")
    if r.authority.get("consumed_at"):
        raise ValueError("cannot approve consumed authority; reconciliation and a new decision are required")
    if not r.request.get("action_hash"):
        raise ValueError("cannot approve without an action commitment")
    approver_snapshot = approver_authority_snapshot(
        bundles.resolve(r.workflow), approver, approver_role
    )
    if approver_snapshot is None:
        raise PermissionError(f"role '{approver_role}' is not authorized to approve this workflow")
    r.authority |= {
        "approver": approver,
        "approver_role": approver_role,
        "approval_method": "explicit",
        "approved_at": now_iso(),
        "authority_basis": r.request.get("requester_authority", "unspecified"),
        "approval_scope": scope or r.request["requested_action"],
        "action_hash": r.request["action_hash"],
        "approver_authority_snapshot": approver_snapshot,
        "approver_authority_hash": sha256_of(approver_snapshot),
        "approval_expires_at": (
            datetime.now(timezone.utc) + timedelta(seconds=approval_ttl_seconds)
        ).isoformat(),
        "separation_of_duties_ok": approver != r.request["requester"],
        "authorization_use": "single_use",
        "consumed_at": None,
        "consumed_by_execution_hash": None,
    }
    if not r.authority["separation_of_duties_ok"]:
        r.flag("SoD violation: approver is the requester")
    r.status = AUTHORIZED
    return r


def seal(r: Receipt, execution_record: dict, bundles: BundleStore) -> Receipt:
    """The AFTER tense - but only if the world held still.
    Hash divergence between check and execution = TOCTOU: refuse to seal."""
    if r.authority.get("consumed_at"):
        raise ValueError("cannot reuse consumed single-use authority")
    if r.status != AUTHORIZED:
        raise ValueError(f"cannot seal receipt in status '{r.status}'")

    bundle_now = bundles.resolve(r.workflow)
    evidence_now, missing = bundles.evidence_for(r.workflow, r.check.get("evidence_refs", []))
    ctx_now = context_hash(evidence_now)
    authority_now = authority_hash(bundle_now, {
        "actor": r.request.get("requester"),
        "risk_class": r.risk_class,
        "action": r.request.get("requested_action"),
    })
    path_now = resolved_authority_path(bundle_now, {
        "workflow": r.workflow,
        "actor": r.request.get("requester"),
        "risk_class": r.risk_class,
        "action": r.request.get("requested_action"),
        "context_refs": r.check.get("evidence_refs", []),
    })

    executed_at = now_iso()
    execution_action = execution_record.get("canonical_action")
    try:
        execution_action_hash = sha256_of(execution_action) if isinstance(execution_action, dict) else None
        r.execution = dict(execution_record) | {
            "executed_at": executed_at,
            "context_hash_at_execution": ctx_now,
            "action_hash": execution_action_hash,
            "execution_attempted": True,
            "outcome_state": "indeterminate",
            "reconciliation_required": True,
        }
        execution_hash = sha256_of(r.execution)
    except (TypeError, ValueError) as exc:
        execution_action_hash = None
        r.execution = {
            "executed_at": executed_at,
            "execution_attempted": True,
            "outcome_state": "indeterminate",
            "reconciliation_required": True,
            "execution_record_invalid": type(exc).__name__,
        }
        execution_hash = sha256_of(r.execution)
    r.authority["consumed_at"] = now_iso()
    r.authority["consumed_by_execution_hash"] = execution_hash

    if r.execution.get("execution_record_invalid"):
        r.status = NEEDS_HUMAN_REVIEW
        r.flag("execution record was not canonical JSON - reconciliation required")
        return r

    if r.authority.get("approval_method") == "explicit":
        binding_fields = (
            "approver_role",
            "approver_authority_snapshot",
            "approver_authority_hash",
            "approval_expires_at",
        )
        if any(not r.authority.get(field) for field in binding_fields):
            r.status = NEEDS_HUMAN_REVIEW
            r.flag("explicit approval is unbound - reconciliation required")
            return r
        try:
            approval_expired = _expired({"expires_at": r.authority["approval_expires_at"]})
        except (TypeError, ValueError):
            approval_expired = True
        if approval_expired:
            r.status = NEEDS_HUMAN_REVIEW
            r.flag("approval expired before execution - reconciliation required")
            return r
        approver_snapshot_now = approver_authority_snapshot(
            bundle_now,
            r.authority.get("approver", ""),
            r.authority.get("approver_role", ""),
        )
        approver_hash_now = sha256_of(approver_snapshot_now) if approver_snapshot_now else None
        if approver_hash_now != r.authority.get("approver_authority_hash"):
            r.status = NEEDS_HUMAN_REVIEW
            r.flag("approver authority changed before execution - reconciliation required")
            return r

    if r.authority.get("action_hash") is None or execution_action_hash != r.authority["action_hash"]:
        r.status = NEEDS_HUMAN_REVIEW
        r.flag("action commitment changed between approval and execution - sealing refused, re-verification required")
        return r

    if missing or ctx_now != r.check.get("context_hash_at_check"):
        r.status = NEEDS_HUMAN_REVIEW
        r.flag("TOCTOU: context changed between check and use - sealing refused, re-verification required")
        return r

    if authority_now is None or authority_now != r.check.get("authority_hash_at_check"):
        r.status = NEEDS_HUMAN_REVIEW
        r.flag("authority changed between check and consequence - sealing refused, re-verification required")
        return r

    previous_path = r.authority.get("resolved_path")
    if previous_path and (path_now is None or path_now.get("path_hash") != previous_path.get("path_hash")):
        r.status = NEEDS_HUMAN_REVIEW
        r.flag("authority path changed between check and consequence - sealing refused, re-verification required")
        return r

    r.status = SEALED
    r.execution["outcome_state"] = "confirmed"
    r.execution["reconciliation_required"] = False
    r.authority["consumed_by_execution_hash"] = sha256_of(r.execution)
    r.receipt = {
        "replayable": True,
        "sealed_at": now_iso(),
    }
    r.receipt["integrity_hash"] = r.seal_hash()
    return r


def watch(store: ReceiptStore, bundles: BundleStore) -> list[Receipt]:
    """Append a ReopenEvent and child lifecycle when a sealed basis drifts.

    The sealed parent is never mutated. Repeated watches of the same changed
    context are idempotent.
    """
    children = []
    for r in store.all():
        if r.status != SEALED:
            continue
        evidence_now, missing = bundles.evidence_for(r.workflow, r.check.get("evidence_refs", []))
        current_hash = context_hash(evidence_now)
        authority_now = authority_hash(bundles.resolve(r.workflow), {
            "actor": r.request.get("requester"),
            "risk_class": r.risk_class,
            "action": r.request.get("requested_action"),
        })
        previous_path = r.authority.get("resolved_path")
        # Legacy receipts have no path to replay; their authority hash remains authoritative.
        path_now = resolved_authority_path(bundles.resolve(r.workflow), {
            "workflow": r.workflow,
            "actor": r.request.get("requester"),
            "risk_class": r.risk_class,
            "action": r.request.get("requested_action"),
            "context_refs": r.check.get("evidence_refs", []),
        }) if previous_path else None
        evidence_drift = bool(missing) or current_hash != r.check.get("context_hash_at_check")
        previous_authority_hash = r.check.get("authority_hash_at_check")
        authority_drift = previous_authority_hash is not None and authority_now != previous_authority_hash
        previous_path_hash = previous_path.get("path_hash") if previous_path else None
        current_path_hash = path_now.get("path_hash") if path_now else None
        authority_path_drift = previous_path is not None and current_path_hash != previous_path_hash
        previous_dependencies = {
            dependency for dependency in (previous_path or {}).get("dependency_ids", [])
            if dependency.startswith("authority-rule:")
        }
        current_dependencies = {
            dependency for dependency in (path_now or {}).get("dependency_ids", [])
            if dependency.startswith("authority-rule:")
        }
        changed_dependencies = previous_dependencies ^ current_dependencies
        if authority_path_drift and not changed_dependencies:
            changed_dependencies = previous_dependencies & current_dependencies
        if not evidence_drift and not authority_drift and not authority_path_drift:
            continue
        if any(
            event.get("current_context_hash") == current_hash
            and event.get("current_authority_hash") == authority_now
            and event.get("current_authority_path_hash") == current_path_hash
            for event in store.events_for(r.decision_id)
        ):
            continue

        event_id = f"RE-{uuid.uuid4().hex[:12]}"
        child = Receipt(
            decision_id=f"{r.decision_id}-child-{uuid.uuid4().hex[:6]}",
            workflow=r.workflow,
            decision_type=r.decision_type,
            risk_class=r.risk_class,
            status=NEEDS_HUMAN_REVIEW,
            parent_receipt_id=r.decision_id,
            reopen_event_id=event_id,
            request=dict(r.request),
        )
        drift_types = [
            kind for kind, changed in (
                ("evidence", evidence_drift),
                ("authority", authority_drift),
                ("authority_path", authority_path_drift),
            ) if changed
        ]
        drift_label = "+".join(drift_types)
        child.flag(f"{drift_label} drift detected by watcher - re-verification required")
        event = {
            "event_id": event_id,
            "event_type": "ReopenEvent",
            "parent_receipt_id": r.decision_id,
            "child_decision_id": child.decision_id,
            "detected_at": now_iso(),
            "reason": f"{drift_label} drift detected by watcher",
            "previous_context_hash": r.check.get("context_hash_at_check"),
            "current_context_hash": current_hash,
            "missing_evidence_refs": missing,
            "previous_authority_hash": previous_authority_hash,
            "current_authority_hash": authority_now,
            "previous_authority_path_hash": previous_path_hash,
            "current_authority_path_hash": current_path_hash,
            "changed_dependencies": sorted(changed_dependencies) if authority_path_drift else [],
            "drift_types": drift_types,
        }
        store.save_event(event)
        store.save(child)
        children.append(child)
    return children


def _match_rule(bundle: dict, req: dict) -> dict | None:
    """Legacy action-less snapshot lookup; exact action paths use _exact_rules."""
    for rule in bundle.get("authority_rules", []):
        if req["actor"] in rule.get("actors", []) and \
           req.get("risk_class", "high") in rule.get("risk_classes", []):
            return rule
    return None


def _expired(rule: dict) -> bool:
    value = rule.get("expires_at")
    if not value:
        return False
    return datetime.fromisoformat(value.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
