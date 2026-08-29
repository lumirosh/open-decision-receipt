import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "examples" / "jep-hjs-boundary-case"
SCHEMA = ROOT / "schemas" / "decision-receipt.schema.json"


def load(name):
    return json.loads((CASE / name).read_text())


def digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def test_boundary_case_forms_a_non_circular_reference_graph():
    delegation = load("delegation-event.json")
    comparison = load("scope-comparison.json")
    verification = load("verification-event.json")
    receipt = load("decision-receipt.json")
    manifest = load("hjs-manifest.json")

    delegation_hash = digest(delegation)
    comparison_hash = digest(comparison)
    verification_hash = digest(verification)
    receipt_hash = digest(receipt)

    assert delegation["verb"] == "D"
    assert "ref" not in delegation
    assert comparison["inputs"]["delegation_event"] == delegation_hash
    assert verification["verb"] == "V"
    assert verification["ref"] == comparison_hash
    assert receipt["receipt"]["external_event_ids"] == [delegation_hash, verification_hash]
    assert receipt["check"]["evidence_refs"] == [comparison_hash]
    assert manifest["root_event"] == verification_hash
    assert [event["event_hash"] for event in manifest["events"]] == [delegation_hash, verification_hash]
    assert [item["digest"] for item in manifest["evidence"]] == [comparison_hash, receipt_hash]


def test_boundary_case_preserves_the_scope_and_partial_effect_boundaries():
    comparison = load("scope-comparison.json")
    receipt = load("decision-receipt.json")

    assert comparison["comparator"] == {
        "id": "urn:example:scope-containment-comparator",
        "version": "0.1-illustrative",
    }
    assert comparison["verdict"] == "not_contained"
    assert comparison["partial_effects"]["authorized_action_a"] == "committed"
    assert comparison["partial_effects"]["candidate_action_b"] == "not_executed"
    assert receipt["status"] == "needs_human_review"
    assert receipt["execution"]["execution_attempted"] is False
    assert receipt["execution"]["execution_result"] == "blocked_scope_not_contained"
    assert receipt["execution"]["outcome_state"] == "confirmed"
    assert receipt["execution"]["reconciliation_required"] is False
    assert receipt["boundary"]["failure_mode"] == "fail_closed"


def test_boundary_case_receipt_validates_without_claiming_interoperability():
    receipt = load("decision-receipt.json")
    manifest = load("hjs-manifest.json")
    validator = Draft202012Validator(json.loads(SCHEMA.read_text()))

    assert list(validator.iter_errors(receipt)) == []
    assert receipt["claim_boundary"]["runtime_enforcement"] is False
    assert receipt["claim_boundary"]["semantic_containment"] == "external_report_only"
    assert manifest["claim_boundary"]["jep_signature_validation"] == "not_performed"
    assert manifest["claim_boundary"]["interoperability"] == "not_claimed"
