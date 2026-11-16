import json
import inspect
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from dam_verify.engine import BundleStore, approve, canonical_action, verify_action
from integrations.authority_continuity import reference as ac


def approved(tmp_path, ttl=300):
    root = tmp_path / "bundles"
    root.mkdir(exist_ok=True)
    (root / "synthetic.yaml").write_text("""
workflow: synthetic
version: 1
human_gate:
  allowed_roles: [reviewer]
  role_assignments:
    reviewer: [neutral_approver]
authority_rules:
  - actors: [neutral_actor]
    risk_classes: [high]
    allowed_actions: [pay_synthetic]
    denied_actions: []
    requires_human: true
    basis: synthetic-test-policy
""")
    bundles = BundleStore(root)
    receipt = verify_action({"workflow": "synthetic", "actor": "neutral_actor", "action": "pay_synthetic", "params": {"amount": 7}}, bundles)
    assert receipt.status == "needs_human_review"
    approve(receipt, "neutral_approver", bundles, "reviewer", approval_ttl_seconds=ttl)
    return bundles, receipt


def test_real_approval_import_pay_and_one_shot_persists_restart(tmp_path):
    bundles, receipt = approved(tmp_path)
    db = tmp_path / "ledger.sqlite"
    ac.register(db, receipt, generation=1, snapshot="basis-v1", owner="worker", epoch=1)
    changed = {**receipt.request["canonical_action"], "parameters": {"amount": 8}}
    with pytest.raises(ValueError, match="commitment"):
        ac.pay(db, receipt.decision_id, changed, "worker", 1)
    assert ac.pay(db, receipt.decision_id, receipt.request["canonical_action"], "worker", 1) == "paid"
    # pay() closes its connection; the next call reopens the same database.
    with pytest.raises(ValueError, match="consumed"):
        ac.pay(db, receipt.decision_id, receipt.request["canonical_action"], "worker", 1)
    assert ac.effect_count(db) == 1


def test_registration_rejects_unbound_changed_and_expired_receipts(tmp_path):
    _, r = approved(tmp_path)
    db = tmp_path / "ledger.sqlite"
    for mutate in (
        lambda x: setattr(x, "status", "denied"),
        lambda x: x.authority.update(action_hash="wrong"),
        lambda x: x.authority.update(consumed_at="2026-01-01T00:00:00+00:00"),
        lambda x: x.request.update(canonical_action={"tampered": True}),
    ):
        import copy
        bad = copy.deepcopy(r); mutate(bad)
        with pytest.raises(ValueError): ac.register(db, bad, 1, "basis-v1", "worker", 1)
    expired_db = tmp_path / "expired.sqlite"
    r.authority["approval_expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError, match="expired"):
        ac.register(expired_db, r, 1, "basis-v1", "worker", 1)
    with pytest.raises(ValueError): ac.register(tmp_path / "bool.sqlite", r, True, "basis-v1", "worker", 1)


def test_basis_and_owner_drift_refuse_without_consuming(tmp_path):
    bundles, r = approved(tmp_path)
    db = tmp_path / "ledger.sqlite"
    ac.register(db, r, 1, "basis-v1", "worker", 1)
    ac.set_basis(db, generation=2, snapshot="basis-v2", enabled=True)
    with pytest.raises(ValueError, match="basis"):
        ac.pay(db, r.decision_id, r.request["canonical_action"], "worker", 1)
    with pytest.raises(ValueError, match="basis"):
        ac.pay(db, r.decision_id, r.request["canonical_action"], "worker", 1)
    owner_db = tmp_path / "owner.sqlite"
    ac.register(owner_db, r, 1, "basis-v1", "worker", 1)
    ac.transfer(owner_db, r.decision_id, "worker", 1, "other")
    with pytest.raises(ValueError, match="owner"):
        ac.pay(owner_db, r.decision_id, r.request["canonical_action"], "worker", 1)


def test_effect_failure_rolls_back_consumption(tmp_path):
    bundles, r = approved(tmp_path)
    db = tmp_path / "ledger.sqlite"
    ac.register(db, r, 1, "basis-v1", "worker", 1)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TRIGGER fail_effect BEFORE INSERT ON effects BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    with pytest.raises(sqlite3.IntegrityError): ac.pay(db, r.decision_id, r.request["canonical_action"], "worker", 1)
    assert ac.is_consumed(db, r.decision_id) is False


def test_competing_connections_create_one_effect(tmp_path):
    bundles, r = approved(tmp_path)
    db = tmp_path / "ledger.sqlite"
    ac.register(db, r, 1, "basis-v1", "worker", 1)
    def attempt(_):
        try: return ac.pay(db, r.decision_id, r.request["canonical_action"], "worker", 1)
        except ValueError: return "refused"
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(attempt, range(2)))
    assert sorted(outcomes) == ["paid", "refused"]
    assert ac.effect_count(db) == 1


def test_handover_exact_scope_unknown_first_no_pay_and_persistent_hold(tmp_path):
    bundles, r = approved(tmp_path)
    db = tmp_path / "ledger.sqlite"
    ac.register(db, r, 1, "basis-v1", "worker", 1)
    registry = {"decision-a": {"operation": r.decision_id, "approval_id": r.decision_id,
        "action_hash": r.authority["action_hash"], "old_owner": "worker", "old_epoch": 1, "new_owner": "observer"}}
    request = {"decision_id": "decision-a", **registry["decision-a"]}
    ac.handover(db, registry, request)
    assert ac.journal_status(db, r.decision_id) == "UNKNOWN"
    with pytest.raises(ValueError): ac.pay(db, r.decision_id, r.request["canonical_action"], "observer", 2)
    assert ac.reconcile(db, r.decision_id) == "UNKNOWN"
    assert ac.effect_count(db) == 0
    with pytest.raises(ValueError, match="stale"):
        ac.pay(db, r.decision_id, r.request["canonical_action"], "worker", 1)
    assert ac.transfer(db, r.decision_id, "observer", 2, "next") == 3
    with pytest.raises(ValueError, match="hold"):
        ac.pay(db, r.decision_id, r.request["canonical_action"], "next", 3)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT recovery_hold FROM grants").fetchone()[0] == 1
    for bad in ({**request, "approved": True}, {**request, "old_epoch": True}, {**request, "new_owner": "tampered"}):
        with pytest.raises(ValueError): ac.handover(db, registry, bad)


def test_legacy_ordinary_transfer_counterexample_and_positive_reconcile(tmp_path):
    bundles, r = approved(tmp_path)
    db = tmp_path / "ledger.sqlite"
    ac.register(db, r, 1, "basis-v1", "worker", 1)
    ac.transfer(db, r.decision_id, "worker", 1, "new-worker")
    assert ac.pay(db, r.decision_id, r.request["canonical_action"], "new-worker", 2) == "paid"
    assert ac.effect_count(db) == 1
    assert ac.reconcile(db, r.decision_id) == "RECONCILED"


def test_unknown_journal_survives_failed_native_handover(tmp_path):
    _, r = approved(tmp_path)
    db = tmp_path / "ledger.sqlite"
    ac.register(db, r, 1, "basis-v1", "worker", 1)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TRIGGER reject_transfer BEFORE UPDATE OF recovery_hold ON grants BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    record = {"operation": r.decision_id, "approval_id": r.decision_id,
        "action_hash": r.authority["action_hash"], "old_owner": "worker", "old_epoch": 1, "new_owner": "observer"}
    with pytest.raises(sqlite3.IntegrityError):
        ac.handover(db, {"decision": record}, {"decision_id": "decision", **record})
    assert ac.journal_status(db, r.decision_id) == "UNKNOWN"
    assert ac.effect_count(db) == 0


def test_material_basis_change_requires_new_generation(tmp_path):
    _, receipt = approved(tmp_path)
    db = tmp_path / "ledger.sqlite"
    ac.register(db, receipt, 1, "basis-v1", "worker", 1)
    with pytest.raises((ValueError, sqlite3.IntegrityError), match="generation"):
        ac.set_basis(db, 1, "basis-v1", False)
    ac.set_basis(db, 2, "basis-v1", False)
    ac.set_basis(db, 3, "basis-v1", True)
    with pytest.raises(ValueError, match="basis"):
        ac.pay(db, receipt.decision_id, receipt.request["canonical_action"], "worker", 1)
    assert ac.effect_count(db) == 0


def test_client_cannot_backdate_resource_expiry_check(tmp_path):
    _, receipt = approved(tmp_path)
    db = tmp_path / "ledger.sqlite"
    ac.register(db, receipt, 1, "basis-v1", "worker", 1)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE grants SET expires_at=?", ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),))
    assert "now" not in inspect.signature(ac.pay).parameters
    with pytest.raises(ValueError, match="expired"):
        ac.pay(db, receipt.decision_id, receipt.request["canonical_action"], "worker", 1)
    assert ac.effect_count(db) == 0


def test_handover_cannot_downgrade_reconciled_outcome(tmp_path):
    _, receipt = approved(tmp_path)
    db = tmp_path / "ledger.sqlite"
    ac.register(db, receipt, 1, "basis-v1", "worker", 1)
    ac.pay(db, receipt.decision_id, receipt.request["canonical_action"], "worker", 1)
    assert ac.reconcile(db, receipt.decision_id) == "RECONCILED"
    record = {"operation": receipt.decision_id, "approval_id": receipt.decision_id,
              "action_hash": receipt.authority["action_hash"], "old_owner": "worker",
              "old_epoch": 1, "new_owner": "observer"}
    assert ac.handover(db, {"decision": record}, {"decision_id": "decision", **record}) == "RECONCILED"
    assert ac.journal_status(db, receipt.decision_id) == "RECONCILED"
