#!/usr/bin/env python3
"""AP payment run demo on the ODR reference engine: vertical slice and 8-test suite.

Default run (vertical slice):
  Scene 1  Declared roles vs effective credential (authority conformance vs effective privilege)
  Scene 2  A payment run approved at 09:00, a fraud alert at 09:15, the next payment at 09:20
  Scene 3  Business reconciliation: committed, held, queued, and already exposed

--suite runs the full acceptance matrix:
  1 baseline            2 bank details changed     3 fraud alert mid-run
  4 authority hop       5 approver revoked         6 fraud feed unreachable
  7 stale verification  8 declared vs effective rights

Everything is synthetic: invoices, vendors, the IAM inventory, the token cache, the clock and the
execution gate. The gate stands in for a real runtime enforcement point. ODR supplies
decision evidence and verdicts; it does not move money and does not stop anything by itself.

Usage:
    python3 scripts/ap-payment-run-demo.py                 # vertical slice
    python3 scripts/ap-payment-run-demo.py --suite         # all eight tests
    python3 scripts/ap-payment-run-demo.py --suite --out DIR   # also write JSON evidence
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dam_verify.engine as engine_module  # noqa: E402
import dam_verify.receipt as receipt_module  # noqa: E402
from dam_verify.conditions import ObservationsStore, evaluate_conditions, failed_conditions  # noqa: E402
from dam_verify.engine import (  # noqa: E402
    BundleStore, approve, approver_authority_snapshot, canonical_action, seal, verify_action,
)
from dam_verify.receipt import AUTHORIZED, SEALED, sha256_of  # noqa: E402

# ----------------------------------------------------------------- scenario (edit freely)

WORKFLOW = "ap_payment_run"
DAY = "2026-11-02"       # a Monday
PREVIOUS_DAY = "2026-11-01"

CONTROLLER = "controller.priya"
CONTROLLER_ROLE = "ap_controller"
APPROVED_AT = "09:00"
ALERTED_VENDOR = "VENDOR-X"
APPROVAL_TTL_SECONDS = 4 * 3600  # how long the 09:00 run approval stays valid
TOKEN_CACHE_SECONDS = 300  # assumed credential cache for the revocation-latency test

# (invoice id, vendor, amount USD, scheduled execution time)
INVOICES = [
    ("INV-001", "VENDOR-A", 4_200, "09:02"),
    ("INV-002", "VENDOR-B", 7_850, "09:04"),
    ("INV-003", "VENDOR-X", 9_800, "09:06"),
    ("INV-004", "VENDOR-C", 3_100, "09:08"),
    ("INV-005", "VENDOR-D", 11_400, "09:10"),
    ("INV-006", "VENDOR-A", 5_650, "09:12"),
    ("INV-007", "VENDOR-X", 18_500, "09:20"),
    ("INV-008", "VENDOR-B", 6_300, "09:22"),
    ("INV-009", "VENDOR-E", 2_750, "09:24"),
    ("INV-010", "VENDOR-C", 8_900, "09:26"),
    ("INV-011", "VENDOR-X", 4_400, "09:28"),
    ("INV-012", "VENDOR-D", 12_050, "09:30"),
]

VENDOR_MASTER = {
    "VENDOR-A": "acct-A-0417",
    "VENDOR-B": "acct-B-2280",
    "VENDOR-C": "acct-C-7713",
    "VENDOR-D": "acct-D-0952",
    "VENDOR-E": "acct-E-3306",
    "VENDOR-X": "acct-X-5104",
}

# Declared role contract: what each digital worker was appointed to do.
DECLARED_ROLES = {
    "invoice_agent": ["match_invoice"],
    "vendor_master_agent": ["propose_bank_change"],
    "payment_agent": ["pay_invoice"],
}

# Synthetic IAM inventory: what the credential behind each agent can actually do.
# In a real Review this comes from the client's IAM / tool-permission export.
CREDENTIALS = {
    "invoice_agent": "ap-automation-sa",
    "vendor_master_agent": "ap-automation-sa",
    "payment_agent": "ap-automation-sa",
}
CREDENTIAL_PERMISSIONS = {
    "ap-automation-sa": [
        "match_invoice",
        "propose_bank_change",
        "update_vendor_bank",
        "pay_invoice",
        "approve_payment",
    ],
}

BASE_BUNDLE = {
    "workflow": WORKFLOW,
    "version": 1,
    "authority_rules": [
        {
            "actors": ["payment_agent"],
            "risk_classes": ["high"],
            "allowed_actions": ["pay_invoice"],
            "denied_actions": ["update_vendor_bank", "approve_payment"],
            "requires_human": True,
            "basis": "policy://ap/payment-run#v1",
            "required_evidence": ["payment_policy"],
        },
        {
            "actors": ["vendor_master_agent"],
            "risk_classes": ["high"],
            "allowed_actions": ["propose_bank_change"],
            "denied_actions": ["update_vendor_bank", "pay_invoice"],
            "requires_human": True,
            "basis": "policy://ap/vendor-master#v1",
            "required_evidence": ["payment_policy"],
        },
    ],
    "human_gate": {
        "allowed_roles": [CONTROLLER_ROLE],
        "role_assignments": {CONTROLLER_ROLE: [CONTROLLER]},
    },
    # Run policy: an open fraud alert on any payee, or an unverified/stale beneficiary
    # check, pauses the whole run until a human revalidates.
    "conditions": [
        {"condition_id": "fraud-alert-clear", "kind": "evidence", "source_ref": "fraud_alerts",
         "operator": "eq", "expected_value": "none", "max_age_seconds": 3600},
        {"condition_id": "beneficiaries-verified", "kind": "evidence", "source_ref": "beneficiary_check",
         "operator": "eq", "expected_value": "verified", "max_age_seconds": 86400},
    ],
    "evidence_sources": {
        "payment_policy": {"version": 1, "content": "Pay approved invoices to verified beneficiaries only."},
    },
}

CONDITION_REFS = ["beneficiary_check", "fraud_alerts"]


def at(hhmm: str, day: str = DAY) -> str:
    return f"{day}T{hhmm}:00Z"


def base_observations() -> dict:
    return {
        "fraud_alerts": {"observed_value": "none", "last_validated_at": at("08:58")},
        "beneficiary_check": {"observed_value": "verified", "last_validated_at": at("08:55")},
    }


# ----------------------------------------------------------------- simulated clock


class SimClock:
    """One clock for the scenario and the receipts.

    The reference engine reads the wall clock for approval, expiry, execution and seal
    timestamps. The demo drives that clock so receipts carry scenario time, and approval
    expiry is judged at scenario time rather than at the moment the script happens to run.
    """

    def __init__(self, start: str):
        self.current = self._parse(start)

    @staticmethod
    def _parse(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def set(self, value: str) -> None:
        self.current = self._parse(value)

    def now(self) -> datetime:
        return self.current


@contextmanager
def simulated_clock(clock: SimClock):
    class _ScenarioDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = clock.now()
            return current.astimezone(tz) if tz else current.replace(tzinfo=None)

    def _now_iso() -> str:
        return clock.now().astimezone(timezone.utc).isoformat(timespec="seconds")

    saved = (engine_module.datetime, engine_module.now_iso, receipt_module.now_iso)
    engine_module.datetime = _ScenarioDateTime
    engine_module.now_iso = _now_iso
    receipt_module.now_iso = _now_iso
    try:
        yield clock
    finally:
        engine_module.datetime, engine_module.now_iso, receipt_module.now_iso = saved


# ----------------------------------------------------------------- simulation


@dataclass
class World:
    root: Path
    bundle: dict = field(default_factory=lambda: copy.deepcopy(BASE_BUNDLE))
    observations: dict = field(default_factory=base_observations)
    vendor_master: dict = field(default_factory=lambda: dict(VENDOR_MASTER))
    revoked_at: str | None = None

    def bundles(self) -> BundleStore:
        path = self.root / "bundles"
        path.mkdir(exist_ok=True)
        (path / f"{WORKFLOW}.yaml").write_text(yaml.safe_dump(self.bundle))
        return BundleStore(path)

    def observation_store(self) -> ObservationsStore:
        path = self.root / "observations"
        path.mkdir(exist_ok=True)
        (path / f"{WORKFLOW}.yaml").write_text(yaml.safe_dump({"observations": self.observations}))
        return ObservationsStore(path)


Event = tuple[str, str, Callable[[World], None]]  # (time, description, mutation)


def payment_params(invoice: tuple, vendor_master: dict) -> dict:
    inv_id, vendor, amount, _ = invoice
    return {"invoice": inv_id, "payee": vendor, "beneficiary_account": vendor_master[vendor],
            "amount_usd": amount}


def payment_request(invoice: tuple, vendor_master: dict) -> dict:
    return {
        "workflow": WORKFLOW,
        "actor": "payment_agent",
        "action": "pay_invoice",
        "risk_class": "high",
        "context_refs": ["payment_policy"],
        "params": payment_params(invoice, vendor_master),
    }


def gate_check(world: World, receipt, instruction: dict, when: str) -> list[str]:
    """Synthetic pre-commit gate. Consumes ODR evidence; returns the reasons to hold.

    Everything that would make seal() refuse must be checked here first: a refused seal
    after the money has moved is evidence, not prevention.
    """
    reasons = []
    expires_at = receipt.authority.get("approval_expires_at")
    if not expires_at or SimClock._parse(expires_at) <= SimClock._parse(at(when)):
        reasons.append("approval window expired before execution")
    snapshot = approver_authority_snapshot(
        world.bundle, receipt.authority.get("approver", ""), receipt.authority.get("approver_role", "")
    )
    if snapshot is None or sha256_of(snapshot) != receipt.authority.get("approver_authority_hash"):
        reasons.append("approver authority changed since approval")
    if sha256_of(instruction) != receipt.authority.get("action_hash"):
        reasons.append("payment instruction differs from the approved action")
    conditions = evaluate_conditions(
        world.bundle["conditions"],
        world.observation_store().observations_for(WORKFLOW, CONDITION_REFS),
        at(when),
    )
    if not conditions["holds"]:
        reasons.extend(f"{c['condition_id']} ({c['state']})" for c in failed_conditions(conditions))
    return reasons


def simulate(events: list[Event], *, verbose: bool = False, initial: Callable[[World], None] | None = None,
             approval_ttl_seconds: int = APPROVAL_TTL_SECONDS) -> dict:
    clock = SimClock(at(APPROVED_AT))
    with tempfile.TemporaryDirectory(prefix="odr-ap-") as tmp, simulated_clock(clock):
        return _simulate(Path(tmp), clock, events, verbose, initial, approval_ttl_seconds)


def _simulate(tmp: Path, clock: SimClock, events: list[Event], verbose: bool,
              initial: Callable[[World], None] | None, approval_ttl_seconds: int) -> dict:
    world = World(tmp)
    if initial:
        initial(world)

    bundles = world.bundles()
    observations = world.observation_store()
    approved = []
    for invoice in INVOICES:
        receipt = verify_action(payment_request(invoice, world.vendor_master), bundles, observations,
                                evaluated_at=at(APPROVED_AT))
        receipt = approve(receipt, approver=CONTROLLER, bundles=bundles,
                          approver_role=CONTROLLER_ROLE, approval_ttl_seconds=approval_ttl_seconds)
        assert receipt.status == AUTHORIZED, receipt.findings
        approved.append((invoice, receipt))

    total = sum(inv[2] for inv in INVOICES)
    if verbose:
        print(f"{APPROVED_AT}  {CONTROLLER} approves {len(INVOICES)} invoices, {money(total)} "
              f"(conditions holding: fraud-alert-clear, beneficiaries-verified)")
        print()
        print(f"{'time':<7}{'invoice':<10}{'payee':<11}{'amount':>10}   {'gate':<6}{'receipt'}")
        rule()

    pending = sorted(events, key=lambda e: e[0])
    rows, applied, halted = [], [], False
    for invoice, receipt in approved:
        inv_id, vendor, amount, when = invoice
        clock.set(at(when))
        while pending and pending[0][0] <= when:
            ev_time, description, mutate = pending.pop(0)
            mutate(world)
            applied.append({"time": ev_time, "event": description})
            if verbose:
                print(f"{ev_time}  {description}")
        row = {"invoice": inv_id, "payee": vendor, "amount": amount, "time": when,
               "decision_id": receipt.decision_id}
        if halted:
            rows.append(row | {"gate": "QUEUED", "receipt_status": receipt.status})
            if verbose:
                print(f"{when:<7}{inv_id:<10}{vendor:<11}{money(amount):>10}   {'-':<6}not attempted (run paused)")
            continue

        bundles = world.bundles()
        observations = world.observation_store()
        instruction = canonical_action(WORKFLOW, "pay_invoice", payment_params(invoice, world.vendor_master))
        execution = {"executed_by": "payment_agent", "execution_result": "success",
                     "canonical_action": instruction}
        reasons = gate_check(world, receipt, instruction, when)
        if not reasons:
            sealed = seal(receipt, execution, bundles, observations, evaluated_at=at(when))
            rows.append(row | {"gate": "PASS", "receipt_status": sealed.status, "receipt": sealed.to_dict()})
            if verbose:
                print(f"{when:<7}{inv_id:<10}{vendor:<11}{money(amount):>10}   {'PASS':<6}{sealed.status.upper()}")
            continue

        # Proof of the receipt layer: had an executor ignored the gate, ODR would refuse to seal.
        bypass = seal(copy.deepcopy(receipt), execution, bundles, observations, evaluated_at=at(when))
        rows.append(row | {"gate": "HOLD", "receipt_status": receipt.status, "hold_reasons": reasons,
                           "seal_if_bypassed": bypass.status,
                           "seal_finding": bypass.findings[-1]["finding"] if bypass.findings else None})
        if verbose:
            print(f"{when:<7}{inv_id:<10}{vendor:<11}{money(amount):>10}   {'HOLD':<6}not executed; approval unconsumed")
            print(f"{'':<9}gate: {'; '.join(reasons)}")
            print(f"{'':<9}if the gate were bypassed, ODR seal -> {bypass.status.upper()}: "
                  f"{bypass.findings[-1]['finding']}")
        halted = True
    return {"events": applied, "results": rows, "revoked_at": world.revoked_at}


def counts(run: dict) -> dict:
    rows = run["results"]
    return {
        "sealed": [r["invoice"] for r in rows if r["gate"] == "PASS" and r["receipt_status"] == SEALED],
        "held": [r["invoice"] for r in rows if r["gate"] == "HOLD"],
        "queued": [r["invoice"] for r in rows if r["gate"] == "QUEUED"],
    }


# ----------------------------------------------------------------- events


def fraud_alert(world: World) -> None:
    world.observations["fraud_alerts"] = {"observed_value": ALERTED_VENDOR, "last_validated_at": at("09:15")}


def bank_details_changed(world: World) -> None:
    world.vendor_master[ALERTED_VENDOR] = "acct-X-9921"


def controller_revoked(world: World) -> None:
    world.bundle["human_gate"]["role_assignments"][CONTROLLER_ROLE] = []
    world.revoked_at = "09:18"


def fraud_feed_down(world: World) -> None:
    world.observations.pop("fraud_alerts", None)


def beneficiary_check_from_yesterday(world: World) -> None:
    # Validated 09:13 yesterday: fresh at 09:12 today, stale (older than 24h) from 09:13.
    world.observations["beneficiary_check"] = {
        "observed_value": "verified", "last_validated_at": at("09:13", PREVIOUS_DAY),
    }


ALERT_EVENT: Event = ("09:15", f"FRAUD ALERT on {ALERTED_VENDOR}  (observation updated; nothing re-approved)", fraud_alert)


# ----------------------------------------------------------------- output helpers


def money(value: int) -> str:
    return f"${value:,}"


def rule(char: str = "-") -> None:
    print(char * 78)


def amount_of(invoices: list[str]) -> int:
    lookup = {inv[0]: inv[2] for inv in INVOICES}
    return sum(lookup[i] for i in invoices)


# ----------------------------------------------------------------- slice scenes


def clocked(fn, *args, when: str = APPROVED_AT, **kwargs):
    with simulated_clock(SimClock(at(when))):
        return fn(*args, **kwargs)


def authority_vs_capability() -> dict:
    findings = []
    for agent, declared in DECLARED_ROLES.items():
        credential = CREDENTIALS[agent]
        excess = [p for p in CREDENTIAL_PERMISSIONS[credential] if p not in declared]
        findings.append({"agent": agent, "credential": credential, "declared": declared, "excess": excess})
    with tempfile.TemporaryDirectory(prefix="odr-ap-") as tmp:
        bundles = World(Path(tmp)).bundles()
        attempt = {
            "workflow": WORKFLOW, "actor": "payment_agent", "action": "update_vendor_bank",
            "risk_class": "high", "context_refs": ["payment_policy"],
            "params": {"payee": ALERTED_VENDOR, "new_account": "acct-X-9921"},
        }
        receipt = clocked(verify_action, attempt, bundles)
    return {"findings": findings, "distinct_credentials": sorted({CREDENTIALS[a] for a in DECLARED_ROLES}),
            "conformance_receipt": receipt.to_dict()}


def scene_1() -> dict:
    rule("=")
    print("SCENE 1  DECLARED ROLES vs EFFECTIVE CREDENTIAL")
    rule("=")
    result = authority_vs_capability()
    print(f"{'agent':<22}{'declared to do':<24}{'credential':<20}{'can also do'}")
    rule()
    for f in result["findings"]:
        print(f"{f['agent']:<22}{', '.join(f['declared']):<24}{f['credential']:<20}{', '.join(f['excess'])}")
    rule()
    print(f"Declared roles: {len(DECLARED_ROLES)}   Distinct credentials: {len(result['distinct_credentials'])} "
          f"({', '.join(result['distinct_credentials'])})")
    receipt = result["conformance_receipt"]
    print()
    print("Payment agent asks to update a vendor's bank details:")
    print(f"  ODR authority conformance   {receipt['status'].upper()}  ({receipt['findings'][-1]['finding']})")
    print("  Effective privilege         EXCESS  (the shared credential can still call update_vendor_bank)")
    print()
    print("Finding: the decision record says no; the credential says yes. Only a runtime")
    print("enforcement point bound to a narrower identity turns the 'no' into a stop.")
    return result


def scene_2() -> dict:
    print()
    rule("=")
    print(f"SCENE 2  RUN APPROVED {APPROVED_AT}, FRAUD ALERT 09:15, NEXT PAYMENT 09:20")
    rule("=")
    return simulate([ALERT_EVENT], verbose=True)


def reconciliation(run: dict) -> dict:
    c = counts(run)
    exposed = [r["invoice"] for r in run["results"]
               if r["gate"] == "PASS" and r["payee"] == ALERTED_VENDOR]
    return {
        "committed": c["sealed"],
        "held": c["held"],
        "queued": c["queued"],
        "paid_to_alerted_vendor_before_alert": exposed,
        "amounts_usd": {
            "committed": amount_of(c["sealed"]),
            "held": amount_of(c["held"]),
            "queued": amount_of(c["queued"]),
            "exposed": amount_of(exposed),
        },
    }


BOUNDARY_TEXT = [
    "Synthetic data, IAM inventory, gate and clock. ODR recorded who approved what,",
    "under which conditions, and refused to seal when the basis broke. It did not verify",
    "identities, discover credentials, move money, or stop anything on its own. Stopping is",
    "the runtime enforcement point's job; ODR is the evidence that it should have.",
]


def scene_3(run: dict) -> dict:
    print()
    rule("=")
    print("SCENE 3  RECONCILIATION")
    rule("=")
    summary = reconciliation(run)
    a = summary["amounts_usd"]

    def line(label, items, amount):
        print(f"{label:<40}{len(items):>3}   {money(amount):>10}")

    line("Committed and sealed", summary["committed"], a["committed"])
    line("Held at the gate", summary["held"], a["held"])
    line("Queued, not attempted", summary["queued"], a["queued"])
    rule()
    line(f"Already paid to {ALERTED_VENDOR} before alert", summary["paid_to_alerted_vendor_before_alert"], a["exposed"])
    print()
    print("Action required")
    print(f"  1. Human revalidation of {ALERTED_VENDOR} before the run resumes.")
    for r in run["results"]:
        if r["invoice"] in summary["paid_to_alerted_vendor_before_alert"]:
            print(f"  2. Review {r['invoice']} ({money(r['amount'])}, paid {r['time']}): recall or confirm. "
                  "Sealed receipts are not undone.")
    print("  3. Held and queued invoices need a fresh condition check before they run; the 09:00")
    print("     approval alone is no longer enough.")
    print()
    rule("=")
    print("BOUNDARY")
    for line_text in BOUNDARY_TEXT:
        print(line_text)
    rule("=")
    return summary


# ----------------------------------------------------------------- suite


def first_hold(run: dict) -> dict | None:
    return next((r for r in run["results"] if r["gate"] == "HOLD"), None)


def run_suite() -> list[dict]:
    tests = []

    def run_test(number, title, events, initial=None, extra=None):
        run = simulate(events, initial=initial)
        result = {"test": number, "title": title, "events": run["events"], "counts": counts(run),
                  "first_hold": first_hold(run), "results": run["results"]}
        if extra:
            result |= extra(run)
        tests.append(result)

    run_test(1, "Baseline: run inside the approved window", [])
    run_test(2, "Bank details changed after approval",
             [("09:16", f"vendor_master_agent changes {ALERTED_VENDOR} bank details via shared credential",
               bank_details_changed)])
    run_test(3, "Fraud alert mid-run", [ALERT_EVENT])

    with tempfile.TemporaryDirectory(prefix="odr-ap-") as tmp:
        bundles = World(Path(tmp)).bundles()
        hop = clocked(verify_action, {
            "workflow": WORKFLOW, "actor": "vendor_master_agent", "action": "pay_invoice",
            "risk_class": "high", "context_refs": ["payment_policy"],
            "params": payment_params(INVOICES[6], VENDOR_MASTER),
        }, bundles)
    tests.append({"test": 4, "title": "Authority hop: vendor_master_agent tries to pay",
                  "verdict": hop.status, "finding": hop.findings[-1]["finding"]})

    def revocation_latency(run):
        revoked = run["revoked_at"]
        after = [r for r in run["results"] if r["time"] > revoked and r["gate"] != "QUEUED"]
        accepted = [r["invoice"] for r in after if r["gate"] == "PASS"]
        first_refused = next((r["time"] for r in after if r["gate"] == "HOLD"), None)
        cache_until = (datetime.strptime(revoked, "%H:%M") + timedelta(seconds=TOKEN_CACHE_SECONDS)).strftime("%H:%M")
        return {"revocation": {
            "revoked_at": revoked,
            "decision_layer_actions_accepted_after": accepted,
            "decision_layer_first_refused_at": first_refused,
            "credential_layer_assumed_cache_seconds": TOKEN_CACHE_SECONDS,
            "credential_layer_usable_until": cache_until,
        }}

    run_test(5, "Approver revoked mid-run",
             [("09:18", f"{CONTROLLER} removed from {CONTROLLER_ROLE}", controller_revoked)],
             extra=revocation_latency)
    run_test(6, "Fraud feed unreachable",
             [("09:16", "fraud feed unreachable (no observation)", fraud_feed_down)])
    run_test(7, "Beneficiary verification goes stale",
             [], initial=beneficiary_check_from_yesterday)
    a_vs_c = authority_vs_capability()
    tests.append({"test": 8, "title": "Declared roles vs effective credential",
                  "verdict": a_vs_c["conformance_receipt"]["status"],
                  "distinct_credentials": a_vs_c["distinct_credentials"],
                  "excess": {f["agent"]: f["excess"] for f in a_vs_c["findings"]}})
    return sorted(tests, key=lambda t: t["test"])


def print_suite(tests: list[dict]) -> None:
    rule("=")
    print(f"AP PAYMENT RUN  8-TEST ACCEPTANCE SUITE   (approved {APPROVED_AT} by {CONTROLLER}, "
          f"{len(INVOICES)} invoices)")
    rule("=")
    for t in tests:
        print(f"TEST {t['test']}  {t['title']}")
        for ev in t.get("events", []):
            print(f"  event     {ev['time']}  {ev['event']}")
        if "counts" in t:
            hold = t["first_hold"]
            if hold:
                print(f"  gate      HOLD at {hold['invoice']} {hold['time']}: {'; '.join(hold['hold_reasons'])}")
                print(f"  ODR       seal if bypassed -> {hold['seal_if_bypassed'].upper()}: {hold['seal_finding']}")
            else:
                print("  gate      all PASS")
            c = t["counts"]
            print(f"  run       {len(c['sealed'])} sealed ({money(amount_of(c['sealed']))}) | "
                  f"{len(c['held'])} held | {len(c['queued'])} queued")
        if "revocation" in t:
            r = t["revocation"]
            print(f"  latency   decision layer: {len(r['decision_layer_actions_accepted_after'])} actions accepted "
                  f"after {r['revoked_at']}, first refused {r['decision_layer_first_refused_at']}")
            print(f"            credential layer (assumed {r['credential_layer_assumed_cache_seconds']}s token cache): "
                  f"still usable until {r['credential_layer_usable_until']}")
        if t["test"] == 4:
            print(f"  ODR       {t['verdict'].upper()}: {t['finding']}")
            print("            exact rule check: the payment approval does not travel to another agent")
        if t["test"] == 8:
            print(f"  ODR       {t['verdict'].upper()} for payment_agent update_vendor_bank (authority conformance)")
            print(f"  IAM       {len(DECLARED_ROLES)} declared roles, {len(t['distinct_credentials'])} credential: "
                  f"every agent can call update_vendor_bank (effective privilege)")
        print()
    rule("=")
    print("BOUNDARY")
    for line_text in BOUNDARY_TEXT:
        print(line_text)
    print("Test 5's credential layer uses an assumed 300s token cache, not a measurement of any real IAM system.")
    rule("=")


# ----------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", action="store_true", help="run all eight acceptance tests")
    parser.add_argument("--out", type=Path, help="directory to write JSON evidence")
    args = parser.parse_args(argv)

    outputs: dict[str, object] = {}
    if args.suite:
        tests = run_suite()
        print_suite(tests)
        outputs["suite.json"] = tests
    else:
        s1 = scene_1()
        s2 = scene_2()
        s3 = scene_3(s2)
        outputs |= {
            "scene1-authority-vs-capability.json": s1,
            "scene2-run.json": s2,
            "scene3-reconciliation.json": s3,
        }

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        for name, payload in outputs.items():
            (args.out / name).write_text(json.dumps(payload, indent=2))
        print(f"\nWrote evidence to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
