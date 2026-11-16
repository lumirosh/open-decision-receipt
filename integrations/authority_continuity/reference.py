"""Small, synthetic SQLite admission and recovery-hold example; not enforcement."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dam_verify.engine import BundleStore, approve, canonical_action, verify_action
from dam_verify.receipt import AUTHORIZED, sha256_of

DDL = """
CREATE TABLE IF NOT EXISTS basis(id INTEGER PRIMARY KEY CHECK(id=1), generation INTEGER NOT NULL,
 snapshot TEXT NOT NULL, enabled INTEGER NOT NULL CHECK(enabled IN (0,1)));
CREATE TABLE IF NOT EXISTS grants(operation TEXT PRIMARY KEY, receipt_id TEXT NOT NULL UNIQUE,
 action TEXT NOT NULL, action_hash TEXT NOT NULL, authority_hash TEXT NOT NULL,
 expires_at TEXT NOT NULL, generation INTEGER NOT NULL, snapshot TEXT NOT NULL,
 owner TEXT NOT NULL, epoch INTEGER NOT NULL, consumed INTEGER NOT NULL DEFAULT 0,
 recovery_hold INTEGER NOT NULL DEFAULT 0);
CREATE TRIGGER IF NOT EXISTS basis_generation_monotonic BEFORE UPDATE OF generation ON basis
WHEN NEW.generation < OLD.generation BEGIN SELECT RAISE(ABORT, 'basis generation cannot decrease'); END;
CREATE TRIGGER IF NOT EXISTS basis_change_requires_generation BEFORE UPDATE ON basis
WHEN (NEW.snapshot <> OLD.snapshot OR NEW.enabled <> OLD.enabled) AND NEW.generation <= OLD.generation
BEGIN SELECT RAISE(ABORT, 'basis change requires a new generation'); END;
CREATE TABLE IF NOT EXISTS effects(operation TEXT PRIMARY KEY, action_hash TEXT NOT NULL, owner TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS journal(operation TEXT PRIMARY KEY, status TEXT NOT NULL, detail TEXT NOT NULL);
INSERT OR IGNORE INTO basis VALUES(1,1,'basis-v1',1);
"""


@contextmanager
def _connect(path):
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        conn.executescript(DDL)
        yield conn
    finally:
        conn.close()


def _int(value, name, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(f"invalid {name}")
    return value


def _expiry(receipt):
    expiry = receipt.authority.get("approval_expires_at")
    if not isinstance(expiry, str):
        raise ValueError("missing approval expiry")
    try:
        value = datetime.fromisoformat(expiry)
    except ValueError as exc:
        raise ValueError("invalid approval expiry") from exc
    if value.tzinfo is None or value <= datetime.now(timezone.utc):
        raise ValueError("approval expired")
    return value.isoformat()


def register(path, receipt, generation, snapshot, owner, epoch):
    """Import an actual, unused ODR authorization as trusted fixture input."""
    generation, epoch = _int(generation, "generation"), _int(epoch, "epoch")
    if receipt.status != AUTHORIZED or not receipt.decision_id:
        raise ValueError("receipt is not authorized")
    action = receipt.request.get("canonical_action")
    digest = receipt.request.get("action_hash")
    approver_snapshot = receipt.authority.get("approver_authority_snapshot")
    expected_action = canonical_action(receipt.workflow, receipt.decision_type, receipt.request.get("params"))
    if (not isinstance(action, dict) or action != expected_action or sha256_of(action) != digest
            or receipt.authority.get("action_hash") != digest
            or receipt.authority.get("approval_method") != "explicit"
            or receipt.authority.get("approval_scope") != receipt.decision_type
            or receipt.authority.get("authorization_use") != "single_use"
            or receipt.authority.get("consumed_at") is not None
            or not receipt.authority.get("approver") or not receipt.authority.get("approver_role")
            or not isinstance(approver_snapshot, dict)
            or approver_snapshot.get("approver") != receipt.authority.get("approver")
            or approver_snapshot.get("approver_role") != receipt.authority.get("approver_role")
            or receipt.authority.get("approver_authority_hash") != sha256_of(approver_snapshot)
            or not receipt.check.get("authority_hash_at_check")):
        raise ValueError("receipt is unbound or consumed")
    expires = _expiry(receipt)

    with _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT generation,snapshot,enabled FROM basis WHERE id=1").fetchone()
        if current != (generation, snapshot, 1):
            raise ValueError("basis does not match registration")
        conn.execute("INSERT INTO grants VALUES(?,?,?,?,?,?,?,?,?,?,0,0)",
                     (receipt.decision_id, receipt.decision_id, json.dumps(action, sort_keys=True), digest,
                      receipt.check.get("authority_hash_at_check") or "", expires, generation, snapshot,
                      owner, epoch))
        conn.commit()
    return receipt.decision_id


def _row(conn, operation):
    row = conn.execute("SELECT action,action_hash,expires_at,generation,snapshot,owner,epoch,consumed,recovery_hold FROM grants WHERE operation=?", (operation,)).fetchone()
    if row is None:
        raise ValueError("grant not found")
    return row


def pay(path, operation, action, owner, epoch):
    """Atomically validate, consume and record one synthetic local effect."""
    epoch = _int(epoch, "epoch")
    encoded = json.dumps(action, sort_keys=True)
    digest = sha256_of(action)
    with _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = _row(conn, operation)
            stored_action, stored_hash, expires, generation, snapshot, current_owner, current_epoch, consumed, hold = row
            basis = conn.execute("SELECT generation,snapshot,enabled FROM basis WHERE id=1").fetchone()
            if (basis != (generation, snapshot, 1) or sha256_of(action) != stored_hash
                    or encoded != stored_action): raise ValueError("basis or action commitment changed")
            if (owner, epoch) != (current_owner, current_epoch): raise ValueError("owner epoch is stale")
            if hold: raise ValueError("recovery hold")
            if consumed: raise ValueError("grant consumed")
            expiry = datetime.fromisoformat(expires)
            if expiry <= datetime.now(timezone.utc): raise ValueError("approval expired")
            conn.execute("UPDATE grants SET consumed=1 WHERE operation=?", (operation,))
            conn.execute("INSERT INTO effects VALUES(?,?,?)", (operation, digest, owner))
            conn.commit()
            return "paid"
        except Exception:
            conn.rollback()
            raise


def set_basis(path, generation, snapshot, enabled):
    generation = _int(generation, "generation")
    if type(enabled) is not bool: raise ValueError("invalid enabled")
    with _connect(path) as conn:
        conn.execute("UPDATE basis SET generation=?,snapshot=?,enabled=? WHERE id=1", (generation, snapshot, int(enabled)))


def transfer(path, operation, old_owner, old_epoch, new_owner):
    old_epoch = _int(old_epoch, "epoch")
    with _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute("UPDATE grants SET owner=?,epoch=epoch+1 WHERE operation=? AND owner=? AND epoch=?", (new_owner, operation, old_owner, old_epoch))
        if cur.rowcount != 1: raise ValueError("owner transfer conflict")
        conn.commit()
    return old_epoch + 1


def _decision(registry, requested):
    if not isinstance(registry, dict) or not isinstance(requested, dict): raise ValueError("invalid handover scope")
    decision_id = requested.get("decision_id")
    record = registry.get(decision_id)
    fields = {"operation", "approval_id", "action_hash", "old_owner", "old_epoch", "new_owner"}
    if (not isinstance(record, dict) or set(record) != fields or set(requested) != fields | {"decision_id"}
        or type(record.get("old_epoch")) is not int or record["old_epoch"] < 1
        or type(requested.get("old_epoch")) is not int or requested != {"decision_id": decision_id, **record}):
        raise ValueError("handover scope mismatch")
    return record


def handover(path, registry, requested):
    record = _decision(registry, requested)
    with _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = _row(conn, record["operation"])
        _, digest, _, _, _, owner, epoch, _, _ = row
        if (record["approval_id"] != record["operation"] or record["action_hash"] != digest
                or (record["old_owner"], record["old_epoch"]) != (owner, epoch)):
            raise ValueError("handover binding conflict")
        conn.execute("INSERT INTO journal VALUES(?,?,?) ON CONFLICT(operation) DO UPDATE SET status='UNKNOWN',detail=excluded.detail WHERE journal.status <> 'RECONCILED'",
                     (record["operation"], "UNKNOWN", json.dumps({"decision_id": requested["decision_id"]}, sort_keys=True)))
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE grants SET owner=?,epoch=epoch+1,recovery_hold=1 WHERE operation=? AND owner=? AND epoch=?",
                     (record["new_owner"], record["operation"], owner, epoch))
        if conn.execute("SELECT changes()").fetchone()[0] != 1:
            conn.rollback()
            raise ValueError("handover owner conflict")
        conn.commit()
    return journal_status(path, record["operation"])


def reconcile(path, operation):
    with _connect(path) as conn:
        effect = conn.execute("SELECT action_hash FROM effects WHERE operation=?", (operation,)).fetchone()
        grant = conn.execute("SELECT action_hash FROM grants WHERE operation=?", (operation,)).fetchone()
        status = "RECONCILED" if effect and grant and effect[0] == grant[0] else "UNKNOWN"
        conn.execute("INSERT INTO journal VALUES(?,?,?) ON CONFLICT(operation) DO UPDATE SET status=excluded.status WHERE journal.status <> 'RECONCILED'", (operation, status, "local synthetic effect lookup"))
        return conn.execute("SELECT status FROM journal WHERE operation=?", (operation,)).fetchone()[0]


def journal_status(path, operation):
    with _connect(path) as conn:
        row = conn.execute("SELECT status FROM journal WHERE operation=?", (operation,)).fetchone()
        return row[0] if row else None


def effect_count(path):
    with _connect(path) as conn: return conn.execute("SELECT count(*) FROM effects").fetchone()[0]


def is_consumed(path, operation):
    with _connect(path) as conn:
        row = conn.execute("SELECT consumed FROM grants WHERE operation=?", (operation,)).fetchone()
        return bool(row and row[0])


def demo(out=None):
    temporary = tempfile.TemporaryDirectory() if out is None else None
    root = Path(out or temporary.name)
    root.mkdir(parents=True, exist_ok=True)
    policy = root / "policy"
    policy.mkdir(exist_ok=True)
    (policy / "synthetic.yaml").write_text("workflow: synthetic\nversion: 1\nhuman_gate:\n  allowed_roles: [reviewer]\n  role_assignments:\n    reviewer: [neutral_approver]\nauthority_rules:\n  - actors: [neutral_actor]\n    risk_classes: [high]\n    allowed_actions: [pay_synthetic]\n    denied_actions: []\n    requires_human: true\n    basis: synthetic-policy\n")
    bundles = BundleStore(policy)
    receipt = verify_action({"workflow":"synthetic","actor":"neutral_actor","action":"pay_synthetic","params":{"amount":7}}, bundles)
    approve(receipt, "neutral_approver", bundles, "reviewer")
    db = root / "reference.sqlite"
    register(db, receipt, 1, "basis-v1", "worker", 1)
    pay(db, receipt.decision_id, canonical_action("synthetic", "pay_synthetic", {"amount":7}), "worker", 1)
    registry = {"decision-demo": {"operation": receipt.decision_id, "approval_id": receipt.decision_id, "action_hash": receipt.authority["action_hash"], "old_owner":"worker", "old_epoch":1, "new_owner":"observer"}}
    handover(db, registry, {"decision_id":"decision-demo", **registry["decision-demo"]})
    print(json.dumps({"receipt_status":receipt.status,"handover":journal_status(db, receipt.decision_id),"reconcile":reconcile(db, receipt.decision_id),"effects":effect_count(db)}, sort_keys=True))
    if temporary: temporary.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    demo(parser.parse_args().out)
