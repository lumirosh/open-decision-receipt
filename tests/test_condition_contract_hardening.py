"""Fail-closed contract tests for Theresa's condition semantics."""
import copy
from pathlib import Path

import yaml

from dam_verify.conditions import (
    HOLDING,
    UNKNOWN,
    ObservationsStore,
    evaluate_condition,
    evaluate_conditions,
    condition_definition_hash,
)
from dam_verify.engine import BundleStore, approve, authority_hash, revalidate, verify_action
from dam_verify.receipt import AUTHORIZED, NEEDS_HUMAN_REVIEW

FIXTURE = Path(__file__).parent / "fixtures" / "conditioned_containment.yaml"
NOW = "2026-08-17T12:00:00Z"
FRESH = "2026-08-17T11:59:00Z"


def _bundle_store(tmp_path, mutate=None):
    root = tmp_path / "bundles"
    root.mkdir(parents=True)
    bundle = yaml.safe_load(FIXTURE.read_text())
    if mutate:
        mutate(bundle)
    (root / "conditioned_containment.yaml").write_text(yaml.safe_dump(bundle))
    return BundleStore(root)


def _observations(tmp_path, values):
    root = tmp_path / "observations"
    root.mkdir(exist_ok=True)
    (root / "conditioned_containment.yaml").write_text(yaml.safe_dump({"observations": values}))
    return ObservationsStore(root)


def _request(compensation=None):
    request = {
        "actor": "containment_agent_v2",
        "workflow": "conditioned_containment",
        "action": "isolate_host",
        "risk_class": "high",
        "context_refs": ["threat_intel_indicator", "asset_criticality"],
        "params": {"host": "HOST-7734"},
    }
    if compensation is not None:
        request["compensation"] = compensation
    return request


def _holding():
    return {
        "threat_intel_indicator": {"observed_value": "ACTIVE", "last_validated_at": FRESH},
        "asset_criticality": {"observed_value": "TIER2", "last_validated_at": FRESH},
    }


def test_condition_definition_is_bound_into_authority_hash(tmp_path):
    original = _bundle_store(tmp_path)
    request = _request()
    before = authority_hash(original.resolve("conditioned_containment"), request)

    bundle = original.resolve("conditioned_containment")
    bundle["conditions"][0]["expected_value"] = "REVOKED"
    (original.root / "conditioned_containment.yaml").write_text(yaml.safe_dump(bundle))

    assert authority_hash(original.resolve("conditioned_containment"), request) != before


def test_invalid_or_missing_validation_timestamp_is_unknown():
    definition = {"operator": "eq", "expected_value": "ACTIVE", "max_age_seconds": 300}
    assert evaluate_condition(definition, {"observed_value": "ACTIVE"}, NOW) == UNKNOWN
    assert evaluate_condition(definition, {"observed_value": "ACTIVE", "last_validated_at": "not-a-time"}, NOW) == UNKNOWN
    assert evaluate_condition(definition, {"observed_value": "ACTIVE", "last_validated_at": FRESH}, "not-a-time") == UNKNOWN


def test_unsupported_operator_and_future_observation_fail_unknown():
    assert evaluate_condition(
        {"operator": "contains", "expected_value": "ACTIVE"},
        {"observed_value": "ACTIVE", "last_validated_at": FRESH},
        NOW,
    ) == UNKNOWN
    assert evaluate_condition(
        {"operator": "eq", "expected_value": "ACTIVE", "max_age_seconds": 300},
        {"observed_value": "ACTIVE", "last_validated_at": "2026-08-17T12:01:00Z"},
        NOW,
    ) == UNKNOWN


def test_timezone_offsets_are_converted_not_relabelled():
    # 13:29 +01:30 is 11:59Z, one minute before NOW.
    assert evaluate_condition(
        {"operator": "eq", "expected_value": "ACTIVE", "max_age_seconds": 300},
        {"observed_value": "ACTIVE", "last_validated_at": "2026-08-17T13:29:00+01:30"},
        NOW,
    ) == HOLDING


def test_pause_names_failed_and_still_holding_condition_ids(tmp_path):
    bundles = _bundle_store(tmp_path)
    values = _holding()
    values["threat_intel_indicator"]["observed_value"] = "REVOKED"
    receipt = verify_action(
        _request(), bundles, _observations(tmp_path, values), evaluated_at=NOW
    )

    assert receipt.status == NEEDS_HUMAN_REVIEW
    assert receipt.check["revalidation_scope"] == ["threat_indicator_active"]
    assert receipt.check["still_holding"] == ["host_not_critical"]
    assert receipt.check["failed_conditions"][0]["condition_id"] == "threat_indicator_active"
    assert receipt.check["failed_conditions"][0]["expected"] == "ACTIVE"


def test_bound_k_of_n_is_exactly_matched_evaluated_and_recorded(tmp_path):
    approved = {
        "mode": "k_of_n",
        "k": 1,
        "members": ["host_not_critical", "threat_indicator_active"],
    }

    def bind(bundle):
        bundle["authority_rules"][0]["compensation"] = copy.deepcopy(approved)

    bundles = _bundle_store(tmp_path, bind)
    values = _holding()
    values["threat_intel_indicator"]["observed_value"] = "REVOKED"
    receipt = verify_action(
        _request(copy.deepcopy(approved)), bundles,
        _observations(tmp_path, values), evaluated_at=NOW,
    )

    assert receipt.status == AUTHORIZED
    assert receipt.check["conditions"]["compensation"]["applied"] is True
    assert receipt.check["conditions"]["compensation"]["authority_hash"] == receipt.check["authority_hash_at_check"]
    assert receipt.check["failed_conditions"][0]["condition_id"] == "threat_indicator_active"


def test_mismatched_or_malformed_compensation_fails_closed(tmp_path):
    approved = {"mode": "k_of_n", "k": 1, "members": ["host_not_critical", "threat_indicator_active"]}

    def bind(bundle):
        bundle["authority_rules"][0]["compensation"] = copy.deepcopy(approved)

    bundles = _bundle_store(tmp_path, bind)
    observations = _observations(tmp_path, _holding())
    mismatch = {"mode": "k_of_n", "k": 2, "members": approved["members"]}
    assert verify_action(_request(mismatch), bundles, observations, evaluated_at=NOW).status != AUTHORIZED

    def malformed(bundle):
        bundle["authority_rules"][0]["compensation"] = {"mode": "k_of_n", "k": 3, "members": ["host_not_critical"]}

    malformed_bundles = _bundle_store(tmp_path / "malformed", malformed)
    malformed_obs = _observations(tmp_path / "malformed", _holding())
    assert verify_action(_request(), malformed_bundles, malformed_obs, evaluated_at=NOW).status != AUTHORIZED


def test_revalidating_different_condition_does_not_resume(tmp_path):
    bundles = _bundle_store(tmp_path)
    values = _holding()
    values["threat_intel_indicator"]["observed_value"] = "REVOKED"
    paused = verify_action(
        _request(), bundles, _observations(tmp_path, values), evaluated_at=NOW
    )

    restored = _observations(tmp_path, _holding())
    result = revalidate(
        paused,
        bundles,
        restored,
        evaluated_at=NOW,
        condition_ids=["host_not_critical"],
    )
    assert result.status == NEEDS_HUMAN_REVIEW


def test_human_required_rule_is_not_policy_authorized_by_revalidation(tmp_path):
    def require_human(bundle):
        bundle["authority_rules"][0]["requires_human"] = True

    bundles = _bundle_store(tmp_path, require_human)
    values = _holding()
    values["threat_intel_indicator"]["observed_value"] = "REVOKED"
    paused = verify_action(
        _request(), bundles, _observations(tmp_path, values), evaluated_at=NOW
    )

    result = revalidate(paused, bundles, _observations(tmp_path, _holding()), evaluated_at=NOW, condition_ids=["threat_indicator_active"])
    assert result.status == NEEDS_HUMAN_REVIEW

    result = revalidate(
        paused, bundles, _observations(tmp_path, _holding()), evaluated_at=NOW,
        condition_ids=["threat_indicator_active"], approver="nobody", approver_role="wrong-role",
    )
    assert result.status == NEEDS_HUMAN_REVIEW


def test_direct_approval_cannot_bypass_failed_condition_revalidation(tmp_path):
    def require_human(bundle):
        bundle["authority_rules"][0]["requires_human"] = True
        bundle["human_gate"] = {
            "allowed_roles": ["change_authority"],
            "role_assignments": {"change_authority": ["named-change-authority"]},
        }

    bundles = _bundle_store(tmp_path, require_human)
    values = _holding()
    values["threat_intel_indicator"]["observed_value"] = "REVOKED"
    paused = verify_action(
        _request(), bundles, _observations(tmp_path, values), evaluated_at=NOW
    )

    try:
        approve(
            paused, approver="named-change-authority", bundles=bundles,
            approver_role="change_authority",
        )
    except ValueError as exc:
        assert "revalidation" in str(exc)
    else:
        raise AssertionError("direct approval bypassed failed-condition revalidation")


def test_scoped_revalidation_refuses_changed_authority_contract(tmp_path):
    bundles = _bundle_store(tmp_path)
    values = _holding()
    values["threat_intel_indicator"]["observed_value"] = "REVOKED"
    paused = verify_action(
        _request(), bundles, _observations(tmp_path, values), evaluated_at=NOW
    )

    bundle = bundles.resolve("conditioned_containment")
    bundle["conditions"][0]["expected_value"] = "REVOKED"
    (bundles.root / "conditioned_containment.yaml").write_text(yaml.safe_dump(bundle))

    result = revalidate(
        paused, bundles, _observations(tmp_path, values), evaluated_at=NOW,
        condition_ids=["threat_indicator_active"],
    )
    assert result.status == NEEDS_HUMAN_REVIEW
    assert any("authority contract changed" in item["finding"] for item in result.findings)


def test_revalidation_cannot_bypass_missing_evidence_pause(tmp_path):
    bundles = _bundle_store(tmp_path)
    bundle = bundles.resolve("conditioned_containment")
    del bundle["evidence_sources"]["threat_intel_indicator"]
    (bundles.root / "conditioned_containment.yaml").write_text(yaml.safe_dump(bundle))
    paused = verify_action(
        _request(), bundles, _observations(tmp_path, _holding()), evaluated_at=NOW
    )
    assert paused.check["missing"] == ["threat_intel_indicator"]

    result = revalidate(paused, bundles, _observations(tmp_path, _holding()), evaluated_at=NOW)
    assert result.status == NEEDS_HUMAN_REVIEW
    assert result.check["missing"] == ["threat_intel_indicator"]


def test_revalidation_never_resets_consumed_authority(tmp_path):
    bundles = _bundle_store(tmp_path)
    values = _holding()
    values["threat_intel_indicator"]["observed_value"] = "REVOKED"
    paused = verify_action(
        _request(), bundles, _observations(tmp_path, values), evaluated_at=NOW
    )
    paused.authority["consumed_at"] = "2026-08-17T11:00:00Z"

    result = revalidate(
        paused, bundles, _observations(tmp_path, _holding()), evaluated_at=NOW,
        condition_ids=["threat_indicator_active"],
    )
    assert result.status == NEEDS_HUMAN_REVIEW
    assert result.authority["consumed_at"] == "2026-08-17T11:00:00Z"


def test_compensation_cannot_mask_unknown_condition():
    definitions = [
        {"condition_id": "a", "source_ref": "a", "operator": "eq", "expected_value": 1, "max_age_seconds": 60},
        {"condition_id": "b", "source_ref": "b", "operator": "eq", "expected_value": 1, "max_age_seconds": 60},
    ]
    result = evaluate_conditions(
        definitions,
        {"a": {"observed_value": 1, "last_validated_at": FRESH}},
        NOW,
        compensation={"mode": "k_of_n", "k": 1, "members": ["a", "b"]},
        authority_hash="sha256:" + "a" * 64,
    )
    assert result["aggregate"] == UNKNOWN
    assert result["holds"] is False
    assert result["compensation"]["applied"] is False


def test_definition_hash_normalizes_local_aliases():
    old = [{"name": "a", "ref": "evidence://a", "operator": "eq", "expected_value": 1, "max_age_seconds": 60}]
    canonical = [{"condition_id": "a", "source_ref": "evidence://a", "operator": "eq", "expected_value": 1, "max_age_seconds": 60}]
    assert condition_definition_hash(old) == condition_definition_hash(canonical)
