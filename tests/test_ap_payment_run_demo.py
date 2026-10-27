import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ap-payment-run-demo.py"


def load_demo():
    spec = importlib.util.spec_from_file_location("ap_payment_run_demo", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ap_payment_run_vertical_slice(tmp_path, capsys):
    demo = load_demo()
    assert demo.main(["--out", str(tmp_path)]) == 0
    capsys.readouterr()

    scene1 = json.loads((tmp_path / "scene1-authority-vs-capability.json").read_text())
    assert scene1["conformance_receipt"]["status"] == "denied"
    assert all("update_vendor_bank" in f["excess"] for f in scene1["findings"])

    run = json.loads((tmp_path / "scene2-run.json").read_text())
    held = [r for r in run["results"] if r["gate"] == "HOLD"]
    assert [r["invoice"] for r in held] == ["INV-007"]
    assert held[0]["seal_if_bypassed"] == "needs_human_review"
    assert held[0]["receipt_status"] == "authorized"  # approval never consumed

    summary = json.loads((tmp_path / "scene3-reconciliation.json").read_text())
    assert summary["committed"] == ["INV-001", "INV-002", "INV-003", "INV-004", "INV-005", "INV-006"]
    assert summary["queued"] == ["INV-008", "INV-009", "INV-010", "INV-011", "INV-012"]
    assert summary["paid_to_alerted_vendor_before_alert"] == ["INV-003"]
    assert summary["amounts_usd"] == {"committed": 42000, "held": 18500, "queued": 34400, "exposed": 9800}


def test_ap_payment_run_eight_test_suite(tmp_path, capsys):
    demo = load_demo()
    assert demo.main(["--suite", "--out", str(tmp_path)]) == 0
    capsys.readouterr()
    tests = {t["test"]: t for t in json.loads((tmp_path / "suite.json").read_text())}
    assert sorted(tests) == [1, 2, 3, 4, 5, 6, 7, 8]

    assert len(tests[1]["counts"]["sealed"]) == 12
    assert tests[1]["first_hold"] is None

    expected_hold = {
        2: ("payment instruction differs from the approved action", "action commitment changed"),
        3: ("fraud-alert-clear (breached)", "condition not holding at execution (breached)"),
        5: ("approver authority changed since approval", "approver authority changed before execution"),
        6: ("fraud-alert-clear (unknown)", "condition not holding at execution (unknown)"),
        7: ("beneficiaries-verified (stale)", "condition not holding at execution (stale)"),
    }
    for number, (gate_reason, seal_finding) in expected_hold.items():
        hold = tests[number]["first_hold"]
        assert hold["invoice"] == "INV-007", number
        assert gate_reason in hold["hold_reasons"], number
        assert hold["seal_if_bypassed"] == "needs_human_review", number
        assert seal_finding in hold["seal_finding"], number
        assert len(tests[number]["counts"]["sealed"]) == 6, number
        assert len(tests[number]["counts"]["queued"]) == 5, number

    assert tests[4]["verdict"] == "denied"
    assert tests[5]["revocation"]["decision_layer_actions_accepted_after"] == []
    assert tests[5]["revocation"]["decision_layer_first_refused_at"] == "09:20"
    assert tests[8]["verdict"] == "denied"
    assert tests[8]["distinct_credentials"] == ["ap-automation-sa"]


def test_receipts_carry_scenario_time_not_wall_clock(capsys):
    demo = load_demo()
    run = demo.simulate([demo.ALERT_EVENT])
    capsys.readouterr()
    first = next(r for r in run["results"] if r["gate"] == "PASS")["receipt"]
    assert first["authority"]["approved_at"].startswith("2026-11-02T09:00")
    assert first["authority"]["approval_expires_at"].startswith("2026-11-02T13:00")
    assert first["execution"]["executed_at"].startswith("2026-11-02T09:02")
    assert first["receipt"]["sealed_at"].startswith("2026-11-02T09:02")


def test_expired_approval_is_held_at_gate_not_refused_after_payment(capsys):
    demo = load_demo()
    run = demo.simulate([], approval_ttl_seconds=15 * 60)  # approval closes at 09:15
    capsys.readouterr()
    rows = {r["invoice"]: r for r in run["results"]}
    assert rows["INV-006"]["gate"] == "PASS" and rows["INV-006"]["receipt_status"] == "sealed"
    assert rows["INV-007"]["gate"] == "HOLD"
    assert "approval window expired before execution" in rows["INV-007"]["hold_reasons"]
    assert "approval expired" in rows["INV-007"]["seal_finding"]
    # Nothing passed the gate and then failed to seal: no payment moved on an expired approval.
    assert all(r["receipt_status"] == "sealed" for r in run["results"] if r["gate"] == "PASS")


def test_engine_clock_restored_after_simulation():
    demo = load_demo()
    demo.simulate([])
    from dam_verify import engine, receipt
    from datetime import datetime
    assert engine.datetime is datetime
    assert engine.now_iso is receipt.now_iso
