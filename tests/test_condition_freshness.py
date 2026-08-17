"""Theresa per-condition evidence freshness scenario - TDD spec.

Separates immutable, authority-bound condition definitions (operator eq,
expected_value, optional max_age_seconds) from mutable observation snapshots.
States: holding | breached | stale | unknown. Default conjunction (no
compensation); k_of_n honored only when bound in the authority rule itself,
never by a mere 'approved_by' string.
"""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for module_name in list(sys.modules):
    if module_name == "dam_verify" or module_name.startswith("dam_verify."):
        del sys.modules[module_name]

from dam_verify.conditions import (
    BREACHED,
    HOLDING,
    STALE,
    UNKNOWN,
    ObservationsStore,
    compensation_refused,
    condition_definition_hash,
    evaluate_condition,
    evaluate_conditions,
)
from dam_verify.engine import (
    BundleStore,
    ReceiptStore,
    approve,
    check_conditions,
    revalidate,
    seal,
    verify_action,
)
from dam_verify.receipt import AUTHORIZED, DENIED, NEEDS_HUMAN_REVIEW, SEALED, now_iso

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "conditioned_containment.yaml"
EVALUATED_AT = "2026-08-17T12:00:00Z"
FRESH = "2026-08-17T11:59:00Z"   # 60s before evaluated_at
STALE_AT = "2026-08-17T10:00:00Z"  # 2h before evaluated_at (>300s max_age)


@pytest.fixture
def bundle_store(tmp_path):
    d = tmp_path / "bundles"
    d.mkdir()
    (d / "conditioned_containment.yaml").write_text(FIXTURE.read_text())
    return BundleStore(d)


@pytest.fixture
def receipt_store(tmp_path):
    return ReceiptStore(tmp_path / "receipts")


@pytest.fixture
def observations_store(tmp_path):
    return ObservationsStore(tmp_path / "obs")


def _write_observations(tmp_path, workflow, values):
    d = tmp_path / "obs"
    d.mkdir(exist_ok=True)
    (d / f"{workflow}.yaml").write_text(yaml.safe_dump({"observations": values}))
    return ObservationsStore(d)


def _holding_obs():
    return {
        "threat_intel_indicator": {"observed_value": "ACTIVE", "last_validated_at": FRESH},
        "asset_criticality": {"observed_value": "TIER2", "last_validated_at": FRESH},
    }


def _request():
    return {
        "actor": "containment_agent_v2",
        "workflow": "conditioned_containment",
        "action": "isolate_host",
        "risk_class": "high",
        "context_refs": ["threat_intel_indicator", "asset_criticality"],
        "params": {"host": "HOST-7734"},
    }


def _execution():
    return {
        "executed_by": "containment_agent_v2",
        "execution_result": "success",
        "canonical_action": {
            "workflow": "conditioned_containment",
            "action_type": "isolate_host",
            "parameters": {"host": "HOST-7734"},
        },
    }


def _sealed(receipt, bundles, observations):
    if receipt.status == NEEDS_HUMAN_REVIEW:
        receipt = approve(receipt, approver="named-change-authority", bundles=bundles, approver_role="change_authority")
    return seal(receipt, _execution(), bundles, observations=observations, evaluated_at=EVALUATED_AT)


# ---------------------------------------------------------------- unit: hash


def test_condition_definition_hash_deterministic_across_order():
    a = [
        {"name": "x", "ref": "r1", "operator": "eq", "expected_value": "A"},
        {"name": "y", "ref": "r2", "operator": "eq", "expected_value": "B"},
    ]
    b = [
        {"ref": "r2", "expected_value": "B", "name": "y", "operator": "eq"},
        {"expected_value": "A", "ref": "r1", "name": "x", "operator": "eq"},
    ]
    assert condition_definition_hash(a) == condition_definition_hash(b)


def test_condition_definition_hash_changes_on_expected_value():
    a = {"name": "x", "operator": "eq", "expected_value": "A"}
    b = {"name": "x", "operator": "eq", "expected_value": "B"}
    assert condition_definition_hash([a]) != condition_definition_hash([b])


# ---------------------------------------------------------------- unit: states


def test_evaluate_condition_holding():
    assert evaluate_condition(
        {"operator": "eq", "expected_value": "ACTIVE", "max_age_seconds": 300},
        {"observed_value": "ACTIVE", "last_validated_at": FRESH},
        EVALUATED_AT,
    ) == HOLDING


def test_evaluate_condition_breached():
    assert evaluate_condition(
        {"operator": "eq", "expected_value": "ACTIVE", "max_age_seconds": 300},
        {"observed_value": "REVOKED", "last_validated_at": FRESH},
        EVALUATED_AT,
    ) == BREACHED


def test_evaluate_condition_stale():
    assert evaluate_condition(
        {"operator": "eq", "expected_value": "ACTIVE", "max_age_seconds": 300},
        {"observed_value": "ACTIVE", "last_validated_at": STALE_AT},
        EVALUATED_AT,
    ) == STALE


def test_evaluate_condition_unknown_when_missing():
    assert evaluate_condition(
        {"operator": "eq", "expected_value": "ACTIVE", "max_age_seconds": 300},
        None,
        EVALUATED_AT,
    ) == UNKNOWN


def test_stale_takes_precedence_over_breach():
    assert evaluate_condition(
        {"operator": "eq", "expected_value": "ACTIVE", "max_age_seconds": 300},
        {"observed_value": "REVOKED", "last_validated_at": STALE_AT},
        EVALUATED_AT,
    ) == STALE


def test_aggregate_defaults_to_conjunction():
    result = evaluate_conditions(
        [
            {"name": "threat", "ref": "t", "operator": "eq", "expected_value": "ACTIVE", "max_age_seconds": 300},
            {"name": "asset", "ref": "a", "operator": "eq", "expected_value": "TIER2", "max_age_seconds": 300},
        ],
        {
            "t": {"observed_value": "ACTIVE", "last_validated_at": FRESH},
            "a": {"observed_value": "CUSTOMER", "last_validated_at": FRESH},  # breached
        },
        EVALUATED_AT,
    )
    assert result["aggregate"] == BREACHED
    assert result["holds"] is False


def test_aggregate_holding_when_all_hold():
    result = evaluate_conditions(
        [
            {"name": "threat", "ref": "t", "operator": "eq", "expected_value": "ACTIVE", "max_age_seconds": 300},
            {"name": "asset", "ref": "a", "operator": "eq", "expected_value": "TIER2", "max_age_seconds": 300},
        ],
        {
            "t": {"observed_value": "ACTIVE", "last_validated_at": FRESH},
            "a": {"observed_value": "TIER2", "last_validated_at": FRESH},
        },
        EVALUATED_AT,
    )
    assert result["aggregate"] == HOLDING
    assert result["holds"] is True


# ---------------------------------------------------------------- unit: compensation


def test_compensation_refused_without_bound_k_of_n_rule():
    rule = {"compensation": None}
    req = {"compensation": {"k_of_n": {"k": 1, "n": 2}, "approved_by": "theresa"}}
    assert compensation_refused(req.get("compensation"), rule) is True


def test_compensation_allowed_only_when_rule_binds_k_of_n():
    definitions = [
        {"name": "a", "ref": "a", "operator": "eq", "expected_value": 1, "max_age_seconds": 60},
        {"name": "b", "ref": "b", "operator": "eq", "expected_value": 1, "max_age_seconds": 60},
    ]
    compensation = {"mode": "k_of_n", "k": 1, "members": ["a", "b"]}
    rule = {"compensation": compensation}
    assert compensation_refused(compensation, rule, definitions) is False


def test_no_compensation_requested_is_not_refused():
    assert compensation_refused(None, {"compensation": None}) is False


# ---------------------------------------------------------------- integration


def test_all_holding_seals(bundle_store, receipt_store, tmp_path):
    obs = _write_observations(tmp_path, "conditioned_containment", _holding_obs())
    receipt = verify_action(_request(), bundle_store, observations=obs, evaluated_at=EVALUATED_AT)
    assert receipt.status == AUTHORIZED  # requires_human: false -> policy pre-authorized
    receipt = seal(receipt, _execution(), bundle_store, observations=obs, evaluated_at=EVALUATED_AT)
    assert receipt.status == SEALED
    assert receipt.check["conditions"]["holds"] is True


def test_breach_at_check_pauses_with_observed_value(bundle_store, receipt_store, tmp_path):
    bad = _holding_obs()
    bad["threat_intel_indicator"]["observed_value"] = "REVOKED"
    obs = _write_observations(tmp_path, "conditioned_containment", bad)
    receipt = verify_action(_request(), bundle_store, observations=obs, evaluated_at=EVALUATED_AT)
    assert receipt.status == NEEDS_HUMAN_REVIEW
    failed = {f["name"]: f for f in receipt.check["failed_conditions"]}
    assert failed["threat_indicator_active"]["state"] == BREACHED
    assert failed["threat_indicator_active"]["observed_value"] == "REVOKED"


def test_stale_at_check_pauses_distinguished(bundle_store, receipt_store, tmp_path):
    old = _holding_obs()
    old["asset_criticality"]["last_validated_at"] = STALE_AT
    obs = _write_observations(tmp_path, "conditioned_containment", old)
    receipt = verify_action(_request(), bundle_store, observations=obs, evaluated_at=EVALUATED_AT)
    assert receipt.status == NEEDS_HUMAN_REVIEW
    failed = {f["name"]: f for f in receipt.check["failed_conditions"]}
    assert failed["host_not_critical"]["state"] == STALE


def test_seal_refused_on_condition_drift(bundle_store, receipt_store, tmp_path):
    obs = _write_observations(tmp_path, "conditioned_containment", _holding_obs())
    receipt = verify_action(_request(), bundle_store, observations=obs, evaluated_at=EVALUATED_AT)
    assert receipt.status == AUTHORIZED
    bad = _holding_obs()
    bad["threat_intel_indicator"]["observed_value"] = "REVOKED"
    obs_bad = _write_observations(tmp_path, "conditioned_containment", bad)
    receipt = seal(receipt, _execution(), bundle_store, observations=obs_bad, evaluated_at=EVALUATED_AT)
    assert receipt.status == NEEDS_HUMAN_REVIEW
    assert any("condition not holding at execution" in f["finding"] for f in receipt.findings)


def test_post_seal_breach_creates_linked_child(bundle_store, receipt_store, tmp_path):
    obs = _write_observations(tmp_path, "conditioned_containment", _holding_obs())
    parent = _sealed(verify_action(_request(), bundle_store, observations=obs, evaluated_at=EVALUATED_AT), bundle_store, obs)
    receipt_store.save(parent)

    bad = _holding_obs()
    bad["threat_intel_indicator"]["observed_value"] = "REVOKED"
    obs_bad = _write_observations(tmp_path, "conditioned_containment", bad)
    children = check_conditions(receipt_store, bundle_store, obs_bad, evaluated_at=EVALUATED_AT)

    assert len(children) == 1
    child = children[0]
    assert child.status == NEEDS_HUMAN_REVIEW
    assert child.parent_receipt_id == parent.decision_id
    assert receipt_store.load(parent.decision_id).to_dict() == parent.to_dict()  # parent immutable
    failed = {f["name"]: f for f in child.check["failed_conditions"]}
    assert failed["threat_indicator_active"]["state"] == BREACHED
    assert failed["threat_indicator_active"]["observed_value"] == "REVOKED"


def test_post_seal_stale_pause_distinguished(bundle_store, receipt_store, tmp_path):
    obs = _write_observations(tmp_path, "conditioned_containment", _holding_obs())
    parent = _sealed(verify_action(_request(), bundle_store, observations=obs, evaluated_at=EVALUATED_AT), bundle_store, obs)
    receipt_store.save(parent)

    old = _holding_obs()
    old["asset_criticality"]["last_validated_at"] = STALE_AT
    obs_old = _write_observations(tmp_path, "conditioned_containment", old)
    children = check_conditions(receipt_store, bundle_store, obs_old, evaluated_at=EVALUATED_AT)

    assert len(children) == 1
    assert children[0].check["conditions"]["aggregate"] == STALE
    failed = {f["name"]: f for f in children[0].check["failed_conditions"]}
    assert failed["host_not_critical"]["state"] == STALE


def test_scoped_revalidation_resumes_via_linked_child(bundle_store, receipt_store, tmp_path):
    obs = _write_observations(tmp_path, "conditioned_containment", _holding_obs())
    parent = _sealed(verify_action(_request(), bundle_store, observations=obs, evaluated_at=EVALUATED_AT), bundle_store, obs)
    receipt_store.save(parent)

    bad = _holding_obs()
    bad["threat_intel_indicator"]["observed_value"] = "REVOKED"
    obs_bad = _write_observations(tmp_path, "conditioned_containment", bad)
    child = check_conditions(receipt_store, bundle_store, obs_bad, evaluated_at=EVALUATED_AT)[0]
    assert child.status == NEEDS_HUMAN_REVIEW

    restored = _write_observations(tmp_path, "conditioned_containment", _holding_obs())
    resumed = revalidate(child, bundle_store, restored, evaluated_at=EVALUATED_AT)
    assert resumed.status == AUTHORIZED
    resumed = seal(resumed, _execution(), bundle_store, observations=restored, evaluated_at=EVALUATED_AT)
    assert resumed.status == SEALED
    assert resumed.parent_receipt_id == parent.decision_id  # linked child semantics
    assert resumed.check["conditions"]["holds"] is True


def test_revalidate_stays_paused_while_conditions_fail(bundle_store, receipt_store, tmp_path):
    obs = _write_observations(tmp_path, "conditioned_containment", _holding_obs())
    parent = _sealed(verify_action(_request(), bundle_store, observations=obs, evaluated_at=EVALUATED_AT), bundle_store, obs)
    receipt_store.save(parent)

    bad = _holding_obs()
    bad["threat_intel_indicator"]["observed_value"] = "REVOKED"
    child = check_conditions(receipt_store, bundle_store, _write_observations(tmp_path, "conditioned_containment", bad), evaluated_at=EVALUATED_AT)[0]

    still_bad = _write_observations(tmp_path, "conditioned_containment", bad)
    resumed = revalidate(child, bundle_store, still_bad, evaluated_at=EVALUATED_AT)
    assert resumed.status == NEEDS_HUMAN_REVIEW  # still paused


def test_unapproved_compensation_refused(bundle_store, receipt_store, tmp_path):
    req = _request()
    req["compensation"] = {"k_of_n": {"k": 1, "n": 2}, "approved_by": "theresa"}
    obs = _write_observations(tmp_path, "conditioned_containment", _holding_obs())
    receipt = verify_action(req, bundle_store, observations=obs)
    assert receipt.status == DENIED
    assert any("compensation refused" in f["finding"] for f in receipt.findings)


def test_legacy_bundle_without_conditions_is_unchanged(bundle_store, receipt_store, tmp_path):
    # cert_gated_deployment has no conditions: verify+seal must behave exactly as before.
    fixture = Path(__file__).resolve().parent / "fixtures" / "cert_gated_deployment.yaml"
    d = tmp_path / "legacy_bundles"
    d.mkdir()
    (d / "cert_gated_deployment.yaml").write_text(fixture.read_text())
    legacy = BundleStore(d)
    req = {
        "actor": "release_workflow",
        "workflow": "cert_gated_deployment",
        "action": "deploy_certified_workflow",
        "risk_class": "high",
        "context_refs": ["certification_status"],
        "params": {"environment": "production"},
    }
    receipt = approve(
        verify_action(req, legacy),
        approver="operator",
        bundles=legacy,
        approver_role="change_authority",
    )
    receipt = seal(receipt, {"executed_by": "w", "execution_result": "success", "canonical_action": receipt.request["canonical_action"]}, legacy)
    assert receipt.status == SEALED
    assert "conditions" not in receipt.check  # conditions are additive only
