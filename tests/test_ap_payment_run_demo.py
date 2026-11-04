import importlib.util
import json
import sys
from pathlib import Path

import pytest

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
    assert sorted(tests) == list(range(1, 12))

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


def test_feed_trust_scenarios(capsys):
    demo = load_demo()
    scenarios = {(t["test"], t.get("case")): t for t in demo.run_suite()}
    assert {(9, "a"), (9, "b"), (10, "a"), (10, "b")} <= scenarios.keys()

    exposed = scenarios[9, "a"]
    assert exposed["outcome"] == "EXPOSED"
    seventh = next(r for r in exposed["results"] if r["invoice"] == "INV-007")
    assert seventh["gate"] == "PASS" and seventh["receipt_status"] == "sealed"
    assert seventh["payee"] == "VENDOR-X" and seventh["amount"] == 18_500
    assert seventh["receipt"]["check"]["conditions_at_execution"]["conditions"][
        "fraud-alert-clear"]["last_validated_at"] == demo.at("08:58")

    frozen = scenarios[9, "b"]["first_hold"]
    assert frozen["invoice"] == "INV-007" and frozen["gate"] == "HOLD"
    assert frozen["hold_reasons"] == ["fraud-alert-clear (stale)"]
    assert frozen["receipt_status"] == "authorized"
    assert frozen["seal_if_bypassed"] == "needs_human_review"

    silenced = scenarios[10, "a"]["first_hold"]
    assert silenced["invoice"] == "INV-007"
    assert set(silenced["hold_reasons"]) == {
        "fraud-alert-clear-psp (breached)", "fraud-alert-clear-siem (breached)"}
    false_alarm = scenarios[10, "b"]
    assert false_alarm["first_hold"]["invoice"] == "INV-007"
    assert false_alarm["first_hold"]["hold_reasons"] == ["fraud-alert-clear-psp (breached)"]
    assert false_alarm["outcome"] == "delay, not payment"
    assert all(r["time"] < "09:15" for r in false_alarm["results"] if r["gate"] == "PASS")

    demo.print_suite(list(scenarios.values()))
    output = capsys.readouterr().out
    assert "TEST 9a" in output and "EXPOSED" in output
    assert "delay, not payment" in output


def test_source_modes_preserve_truth_and_last_answer():
    demo = load_demo()
    source = demo.Source(truth="none")
    first = source.read(demo.at("09:00"))
    assert first == {"observed_value": "none", "last_validated_at": demo.at("09:00")}
    source.truth, source.mode = "VENDOR-X", "frozen"
    assert source.read(demo.at("09:20")) == first
    source.mode = "down"
    assert source.read(demo.at("09:20")) is None
    source.mode = "silenced"
    assert source.read(demo.at("09:20")) == {
        "observed_value": "none", "last_validated_at": demo.at("09:20")}
    assert source.truth == "VENDOR-X"
    source.mode, source.false_alarm_vendor = "false_alarm", "VENDOR-B"
    assert source.read(demo.at("09:20"))["observed_value"] == "VENDOR-B"
    source.mode = "live"
    assert source.read(demo.at("09:20"))["observed_value"] == "VENDOR-X"


def test_witness_bundle_requires_every_source_without_compensation():
    demo = load_demo()
    bundle = demo.feed_trust_bundle(witnesses=True)
    assert "compensation" not in bundle
    assert all("compensation" not in rule for rule in bundle["authority_rules"])
    witnesses = [c for c in bundle["conditions"] if c["condition_id"].startswith("fraud-alert-clear-")]
    assert {c["source_ref"] for c in witnesses} == {
        "fraud_alerts_bank", "fraud_alerts_psp", "fraud_alerts_siem"}
    assert all(c["operator"] == "eq" and c["expected_value"] == "none"
               and c["max_age_seconds"] == 60 for c in witnesses)

    def initial(world):
        world.bundle = bundle
        for witness in witnesses:
            world.sources[witness["source_ref"]] = demo.Source(truth="none")

    for mode in ("down", "frozen"):
        def interrupt(world):
            world.sources["fraud_alerts_bank"].mode = mode
        run = demo.simulate([("09:15", mode, interrupt)], initial=initial, pull_at_execution=True)
        hold = demo.first_hold(run)
        assert hold["invoice"] == "INV-007"
        state = "unknown" if mode == "down" else "stale"
        assert hold["hold_reasons"] == [f"fraud-alert-clear-bank ({state})"]
        assert hold["seal_if_bypassed"] == "needs_human_review"


def test_blast_radius_caps_the_fooled_gate(capsys):
    demo = load_demo()
    suite = demo.run_suite()
    capped = next((t for t in suite if t["test"] == 11), None)
    assert capped is not None
    hold = capped["first_hold"]
    assert hold["invoice"] == "INV-007"
    assert hold["hold_reasons"] == ["blast-radius cap"]
    assert hold["receipt_status"] == "authorized"
    assert hold["seal_if_bypassed"] == "sealed"  # cap belongs to the gate, not the ODR engine
    assert capped["exposure_usd"]["without_cap"] > capped["exposure_usd"]["with_cap"] == 9_800
    sealed = [r for r in capped["results"] if r["receipt_status"] == "sealed"]
    from datetime import timedelta
    for end in (demo.SimClock._parse(demo.at(r["time"])) for r in sealed):
        start = end - timedelta(minutes=capped["run_cap"]["window_minutes"])
        assert sum(r["amount"] for r in sealed
                   if start < demo.SimClock._parse(demo.at(r["time"])) <= end) <= capped["run_cap"]["usd"]
    demo.print_suite([capped])
    output = capsys.readouterr().out
    assert "without cap" in output and "with cap" in output
    assert "cap is a gate-only rule" in output


def test_cap_is_rolling_all_payee_and_allows_exact_limit(monkeypatch):
    demo = load_demo()
    monkeypatch.setattr(demo, "INVOICES", [
        ("CAP-1", "VENDOR-A", 6_000, "09:02"),
        ("CAP-2", "VENDOR-B", 4_000, "09:04"),
        ("CAP-3", "VENDOR-X", 6_000, "09:12"),
        ("CAP-4", "VENDOR-C", 4_000, "09:14"),
        ("CAP-5", "VENDOR-X", 1, "09:15"),
    ])
    run = demo.simulate([], run_cap={"usd": 10_000, "window_minutes": 10})
    assert demo.counts(run)["sealed"] == ["CAP-1", "CAP-2", "CAP-3", "CAP-4"]
    assert demo.first_hold(run)["invoice"] == "CAP-5"
    assert demo.first_hold(run)["hold_reasons"] == ["blast-radius cap"]


@pytest.mark.parametrize("cap", [
    {}, {"usd": -1, "window_minutes": 30}, {"usd": True, "window_minutes": 30},
    {"usd": 10_000, "window_minutes": 0}, {"usd": 10_000, "window_minutes": -1},
    {"usd": 10_000, "window_minutes": False}, {"usd": 10_000.0, "window_minutes": 30},
    {"usd": "10000", "window_minutes": 30}, {"usd": 10_000, "window_minutes": 30, "typo": 1},
])
def test_invalid_cap_is_rejected(cap):
    demo = load_demo()
    with pytest.raises(ValueError, match="run_cap"):
        demo.simulate([], run_cap=cap)


def test_engine_clock_restored_after_simulation():
    demo = load_demo()
    demo.simulate([])
    from dam_verify import engine, receipt
    from datetime import datetime
    assert engine.datetime is datetime
    assert engine.now_iso is receipt.now_iso
