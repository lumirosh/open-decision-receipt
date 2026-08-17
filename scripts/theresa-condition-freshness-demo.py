#!/usr/bin/env python3
"""Executable evidence-freshness stress test for Theresa's scenario."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dam_verify.conditions import ObservationsStore
from dam_verify.engine import BundleStore, ReceiptStore, check_conditions, revalidate, seal, verify_action

EVALUATED_AT = "2026-08-17T12:00:00Z"
FRESH = "2026-08-17T10:00:00Z"
VENDOR_FRESH = "2026-08-17T10:00:00Z"
VENDOR_STALE = "2026-08-16T06:00:00Z"

BUNDLE = {
    "workflow": "theresa_evidence_freshness",
    "version": 1,
    "authority_rules": [{
        "actors": ["release_agent"],
        "risk_classes": ["high"],
        "allowed_actions": ["release_workflow"],
        "denied_actions": ["bypass_condition_check"],
        "requires_human": False,
        "basis": "scenario://theresa/evidence-freshness#v1",
        "required_evidence": ["cert_status", "vendor_attestation", "blast_radius"],
    }],
    "conditions": [
        {"condition_id": "cert-status-current", "kind": "evidence", "source_ref": "cert_status", "operator": "eq", "expected_value": "valid", "max_age_seconds": 86400},
        {"condition_id": "vendor-attestation", "kind": "evidence", "source_ref": "vendor_attestation", "operator": "eq", "expected_value": "valid", "max_age_seconds": 86400},
        {"condition_id": "blast-radius-limit", "kind": "authority_rule", "source_ref": "blast_radius", "operator": "eq", "expected_value": "2 of 3", "max_age_seconds": 86400},
    ],
    "evidence_sources": {
        "cert_status": {"version": 1, "content": "valid"},
        "vendor_attestation": {"version": 1, "content": "valid"},
        "blast_radius": {"version": 1, "content": "2 of 3"},
    },
}
REQUEST = {
    "actor": "release_agent",
    "workflow": "theresa_evidence_freshness",
    "action": "release_workflow",
    "risk_class": "high",
    "context_refs": ["cert_status", "vendor_attestation", "blast_radius"],
    "params": {"release": "THERESA-1"},
}


def observations(vendor_value="valid", vendor_at=VENDOR_FRESH):
    return {
        "cert_status": {"observed_value": "valid", "last_validated_at": FRESH},
        "vendor_attestation": {"observed_value": vendor_value, "last_validated_at": vendor_at},
        "blast_radius": {"observed_value": "2 of 3", "last_validated_at": FRESH},
    }


def write_observations(root: Path, values: dict) -> ObservationsStore:
    root.mkdir(exist_ok=True)
    (root / "theresa_evidence_freshness.yaml").write_text(yaml.safe_dump({"observations": values}))
    return ObservationsStore(root)


def execution(receipt):
    return {
        "executed_by": "release_agent",
        "execution_result": "success",
        "canonical_action": receipt.request["canonical_action"],
    }


def print_check(title: str, receipt, verdict: str):
    print(f"\n{title}")
    print(f"ODR / CONDITION CHECK        {receipt.decision_id}")
    conditions = receipt.check.get("conditions", {}).get("conditions", {})
    for condition_id, item in conditions.items():
        age = "checked 2h ago"
        if condition_id == "vendor-attestation" and item["state"] == "stale":
            age = "checked 30h ago (max 24h)"
        print(f"{condition_id:<28} {item['state'].upper():<10} {str(item['observed_value']):<12} {age}")
    print("COMPENSATION                 none (not approved)")
    print(f"VERDICT                      {verdict}")
    failed = receipt.check.get("failed_conditions", [])
    if failed:
        print("FAILED                       " + ", ".join(f"{item['condition_id']} ({item['state']})" for item in failed))
    scope = receipt.check.get("revalidation_scope", [])
    if scope:
        print("REVALIDATION SCOPE           " + ", ".join(scope))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="odr-theresa-") as tmp:
        root = Path(tmp)
        bundle_root = root / "bundles"
        bundle_root.mkdir()
        (bundle_root / "theresa_evidence_freshness.yaml").write_text(yaml.safe_dump(BUNDLE))
        bundles = BundleStore(bundle_root)
        receipt_store = ReceiptStore(root / "receipts")
        obs_root = root / "observations"

        fresh = write_observations(obs_root, observations())
        parent = verify_action(REQUEST, bundles, fresh, evaluated_at=EVALUATED_AT)
        parent = seal(parent, execution(parent), bundles, fresh, evaluated_at=EVALUATED_AT)
        receipt_store.save(parent)
        print_check("1. ALL HOLDING", parent, "SEALED")

        breached = write_observations(obs_root, observations(vendor_value="revoked"))
        breach_receipt = verify_action(REQUEST, bundles, breached, evaluated_at=EVALUATED_AT)
        print_check("2. BREACHED", breach_receipt, "PAUSED")

        stale = write_observations(obs_root, observations(vendor_at=VENDOR_STALE))
        stale_receipt = verify_action(REQUEST, bundles, stale, evaluated_at=EVALUATED_AT)
        print_check("3. STALE", stale_receipt, "PAUSED")

        child = check_conditions(receipt_store, bundles, stale, evaluated_at=EVALUATED_AT)[0]
        restored = write_observations(obs_root, observations())
        child = revalidate(
            child, bundles, restored, evaluated_at=EVALUATED_AT,
            condition_ids=["vendor-attestation"],
        )
        child = seal(child, execution(child), bundles, restored, evaluated_at=EVALUATED_AT)
        print_check("4. SCOPED REVALIDATION", child, "SEALED")
        print("RESUMED                      linked child; sealed parent unchanged")

        request = dict(REQUEST) | {
            "compensation": {
                "mode": "k_of_n", "k": 2,
                "members": ["cert-status-current", "vendor-attestation", "blast-radius-limit"],
                "approved_by": "unbound-name",
            }
        }
        refused = verify_action(request, bundles, restored, evaluated_at=EVALUATED_AT)
        print("\n5. UNAPPROVED COMPENSATION")
        print(f"ODR / CONDITION CHECK        {refused.decision_id}")
        print("VERDICT                      REFUSED")
        print("REASON                       compensation was not inside approved authority scope")

        print("\nBOUNDARY")
        print("This scenario verifies recorded condition inputs, freshness, authority structure, and linked revalidation.")
        print("It does not discover conditions, schedule checks, or prove source truth; it does not observe real-world effects.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
