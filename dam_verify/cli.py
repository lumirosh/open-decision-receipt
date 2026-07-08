"""dam verify-action CLI - the cert-drift demo surface.

Usage:
    python -m dam_verify.cli verify   examples/verify-action-deploy.json
    python -m dam_verify.cli approve  <decision_id> --approver operator
    python -m dam_verify.cli seal     <decision_id> --result success
    python -m dam_verify.cli replay   <decision_id>
    python -m dam_verify.cli grammar  <decision_id>
    python -m dam_verify.cli chain

Global options such as --receipts-dir come before the subcommand:
    python -m dam_verify.cli --receipts-dir /tmp/receipts verify examples/verify-action-deploy.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import BundleStore, ReceiptStore, verify_action, approve, seal, watch
from .okf import promote_receipt_bundle

PROJECT = Path(__file__).resolve().parent.parent
DEFAULT_BUNDLES_DIR = PROJECT / "dam" / "action_bundles"
DEFAULT_RECEIPTS_DIR = PROJECT / "data" / "action_receipts"
DEFAULT_OKF_BUNDLES_DIR = PROJECT / "dam" / "bundles"


def _print(r):
    print(json.dumps({
        "decision_id": r.decision_id,
        "status": r.status,
        "workflow": r.workflow,
        "action": r.decision_type,
        "boundary": r.boundary,
        "check": {k: v for k, v in r.check.items() if k != "evidence_seen"},
        "authority": r.authority,
        "findings": r.findings,
    }, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(prog="dam verify-action")
    p.add_argument(
        "--bundles-dir",
        default=str(DEFAULT_BUNDLES_DIR),
        help="Authority bundle directory (default: dam/action_bundles)",
    )
    p.add_argument(
        "--receipts-dir",
        default=str(DEFAULT_RECEIPTS_DIR),
        help="Receipt store directory (default: data/action_receipts)",
    )
    p.add_argument(
        "--okf-bundles-dir",
        default=str(DEFAULT_OKF_BUNDLES_DIR),
        help="OKF/DAM bundle output directory for promote (default: dam/bundles)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("verify");  v.add_argument("action_file")
    a = sub.add_parser("approve"); a.add_argument("decision_id"); a.add_argument("--approver", required=True)
    s = sub.add_parser("seal");    s.add_argument("decision_id"); s.add_argument("--result", default="success")
    sub.add_parser("watch")
    sh = sub.add_parser("show");   sh.add_argument("decision_id")
    rp = sub.add_parser("replay"); rp.add_argument("decision_id")
    g = sub.add_parser("grammar"); g.add_argument("decision_id")
    sub.add_parser("chain")
    pr = sub.add_parser("promote"); pr.add_argument("decision_id"); pr.add_argument("--title", default=None); pr.add_argument("--approve", action="store_true")

    args = p.parse_args(argv)
    bundles = BundleStore(Path(args.bundles_dir))
    receipts = ReceiptStore(Path(args.receipts_dir))

    if args.cmd == "verify":
        req = json.loads(Path(args.action_file).read_text())
        r = verify_action(req, bundles)
        receipts.save(r)
        _print(r)
    elif args.cmd == "approve":
        r = receipts.load(args.decision_id)
        r = approve(r, approver=args.approver)
        receipts.save(r)
        _print(r)
    elif args.cmd == "seal":
        r = receipts.load(args.decision_id)
        r = seal(r, {"executed_by": "workflow", "execution_result": args.result}, bundles)
        receipts.save(r)
        _print(r)
    elif args.cmd == "watch":
        reopened = watch(receipts, bundles)
        print(f"reopened: {len(reopened)}")
        for r in reopened:
            print(f"  {r.decision_id}  {r.findings[-1]['finding']}")
    elif args.cmd == "show":
        r = receipts.load(args.decision_id)
        print(json.dumps(r.to_dict(), indent=2))
    elif args.cmd == "replay":
        print(replay(receipts.load(args.decision_id)))
    elif args.cmd == "grammar":
        from .grammar import compile_action_schema
        print(json.dumps(compile_action_schema(receipts.load(args.decision_id)), indent=2))
    elif args.cmd == "chain":
        ok, broken = receipts.chain.verify()
        print(f"chain intact: {ok}" + ("" if ok else f" - broken at entry {broken}"))
    elif args.cmd == "promote":
        r = receipts.load(args.decision_id)
        out = promote_receipt_bundle(
            r,
            Path(args.okf_bundles_dir),
            approve=args.approve,
            title=args.title,
        )
        if not out["approved"]:
            print("DRY RUN - nothing written. Receipt bundle promotion is human-gated.")
            print(f"Would write: {out['path']}\n")
            print(out["content"])
            print("\nRe-run with promote <decision_id> --approve to write this OKF bundle.")
        else:
            print(f"Promoted receipt {r.decision_id} -> {out['path']}")
            print("  state: verified | verification: dam=verified user=approved")
    return 0


def replay(r) -> str:
    """Render a receipt as the decision story. This is the auditor view."""
    req, chk, auth, exe = r.request, r.check, r.authority, r.execution
    lines = [
        f"DECISION {r.decision_id}  [{r.status.upper()}]",
        f"  workflow   : {r.workflow}  (risk: {r.risk_class})",
        f"  requested  : '{req.get('requested_action')}' by {req.get('requester')} at {req.get('requested_at')}",
        f"  checked    : {chk.get('checked_at', 'never')} against {len(chk.get('evidence_seen', {}))} evidence sources",
        f"               context hash at check: {chk.get('context_hash_at_check', 'n/a')}",
        f"  authority  : {auth.get('approver', 'NONE')} via {auth.get('approval_method', 'n/a')}"
        f" | scope: {auth.get('approval_scope', 'n/a')}",
        f"               basis: {auth.get('authority_basis', 'n/a')} | SoD ok: {auth.get('separation_of_duties_ok', 'n/a')}",
        f"  boundary   : allowed {r.boundary.get('allowed_actions', [])} | {r.boundary.get('failure_mode', 'n/a')}",
        f"  executed   : {exe.get('executed_at', 'not executed')}"
        + (f" | context hash at use: {exe.get('context_hash_at_execution')}" if exe else ""),
        f"  replayable : {r.replayable} | integrity: {r.receipt.get('integrity_hash', 'unsealed')}",
    ]
    if chk.get("context_hash_at_check") and exe.get("context_hash_at_execution"):
        match = chk["context_hash_at_check"] == exe["context_hash_at_execution"]
        lines.append(f"  check==use : {match}" + ("" if match else "  << TOCTOU: world changed between approval and action"))
    for finding in r.findings:
        lines.append(f"  finding    : {finding['finding']}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
