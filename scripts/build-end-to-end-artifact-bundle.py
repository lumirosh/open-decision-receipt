#!/usr/bin/env python3
"""Build one concrete allow/refuse/drift ODR evidence bundle."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dam_verify.engine import BundleStore, ReceiptStore, approve, canonical_action, seal, verify_action, watch
from dam_verify.receipt import DENIED, NEEDS_HUMAN_REVIEW, SEALED


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    fixture = ROOT / "tests" / "fixtures" / "cert_gated_deployment.yaml"
    authority_path = output / "authority-basis.yaml"
    shutil.copyfile(fixture, authority_path)

    allow_request = {
        "actor": "release_workflow",
        "workflow": "cert_gated_deployment",
        "action": "deploy_certified_workflow",
        "risk_class": "high",
        "context_refs": ["certification_status"],
        "params": {"environment": "production", "path": "A"},
    }
    refuse_request = dict(allow_request, action="bypass_gate")
    execution = {
        "executed_by": "release_workflow",
        "execution_result": "success",
        "canonical_action": canonical_action(
            allow_request["workflow"], allow_request["action"], allow_request["params"]
        ),
    }

    write_json(output / "allow-request.json", allow_request)
    write_json(output / "refuse-request.json", refuse_request)
    write_json(output / "execution-evidence.json", execution)

    with tempfile.TemporaryDirectory() as working:
        working = Path(working)
        bundle_dir = working / "bundles"
        bundle_dir.mkdir()
        live_authority = bundle_dir / "cert_gated_deployment.yaml"
        shutil.copyfile(authority_path, live_authority)
        bundles = BundleStore(bundle_dir)
        receipts = ReceiptStore(working / "receipts")

        parent = verify_action(allow_request, bundles)
        assert parent.status == NEEDS_HUMAN_REVIEW
        parent = approve(parent, approver="named-change-authority")
        parent = seal(parent, execution, bundles)
        assert parent.status == SEALED
        receipts.save(parent)

        refused = verify_action(refuse_request, bundles)
        assert refused.status == DENIED

        changed = yaml.safe_load(live_authority.read_text())
        changed["evidence_sources"]["certification_status"]["version"] += 1
        changed["evidence_sources"]["certification_status"]["content"] = (
            "Certification CERT-2214 REVOKED. Scope invalidated."
        )
        live_authority.write_text(yaml.safe_dump(changed, sort_keys=False))

        children = watch(receipts, bundles)
        assert len(children) == 1
        child = children[0]
        event = receipts.events_for(parent.decision_id)[0]
        assert receipts.load(parent.decision_id).to_dict() == parent.to_dict()

    files = {
        "allow-sealed-receipt.json": parent.to_dict(),
        "refuse-receipt.json": refused.to_dict(),
        "reopen-event.json": event,
        "child-revalidation.json": child.to_dict(),
    }
    for name, value in files.items():
        write_json(output / name, value)

    artifact_names = [
        "authority-basis.yaml",
        "allow-request.json",
        "refuse-request.json",
        "execution-evidence.json",
        *files,
    ]
    manifest = {
        "profile": "illustrative certification-gated deployment",
        "claim_boundary": (
            "Demonstrates bounded allow/refuse, immutable sealed-parent preservation, "
            "drift detection, append-only ReopenEvent, and linked revalidation child."
        ),
        "relationships": {
            "sealed_parent": parent.decision_id,
            "reopen_event": event["event_id"],
            "child_lifecycle": child.decision_id,
            "refused_attempt": refused.decision_id,
        },
        "sha256": {name: digest(output / name) for name in artifact_names},
    }
    write_json(output / "manifest.json", manifest)
    print(output)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: build-end-to-end-artifact-bundle.py OUTPUT_DIR")
    target = Path(sys.argv[1])
    main(target.resolve())
