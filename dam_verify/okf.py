"""Promote action Decision Receipts into OKF/DAM bundles.

This is the human-in-the-loop close: verify-action produces the receipt, a human
approves/seals it, then a second explicit promote step turns that receipt into a
verified OKF bundle. Dry run is the default.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import re

from .receipt import Receipt, SEALED


def slugify(text: str, max_len: int = 60) -> str:
    """Filesystem-safe slug from a title."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "untitled"


def render_frontmatter(fm: dict) -> str:
    """Render a small YAML-compatible frontmatter block without framework deps."""
    lines = ["---"]
    for key, val in fm.items():
        if isinstance(val, list):
            lines.append(f"{key}:")
            for item in val:
                lines.append(f"  - {item}")
        elif isinstance(val, dict):
            lines.append(f"{key}:")
            for k, v in val.items():
                lines.append(f"  {k}: {v}")
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines)


def promote_receipt_bundle(
    receipt: Receipt,
    bundles_dir: str | Path = "dam/bundles",
    *,
    approve: bool = False,
    title: str | None = None,
) -> dict:
    """Render or write an OKF decision bundle from a sealed action receipt.

    The receipt must already be sealed. Writing requires approve=True, preserving
    a distinct human promotion gate after action verification.
    """
    if receipt.status != SEALED:
        raise ValueError(f"only sealed receipts can be promoted, got {receipt.status!r}")

    title = title or f"Decision Receipt: {receipt.workflow} / {receipt.decision_type}"
    today = datetime.now(timezone.utc).date().isoformat()
    user_state = "approved" if approve else "pending"
    state = "verified" if approve else "verified_draft"
    fm = {
        "type": "decision",
        "title": title,
        "description": "Human-approved action Decision Receipt promoted from DAM verify-action.",
        "resource": f"receipt:{receipt.decision_id}",
        "source": f"dam.verify-action:{receipt.decision_id}",
        "state": state,
        "evidence": [
            f"receipt:{receipt.decision_id}",
            f"workflow:{receipt.workflow}",
            f"action:{receipt.decision_type}",
            f"context_hash:{receipt.check.get('context_hash_at_check', '')}",
            f"integrity_hash:{receipt.receipt.get('integrity_hash', '')}",
        ],
        "authority_boundary": (
            "Receipt was verified, explicitly approved, and sealed. Promotion "
            "makes it verified knowledge only; reuse, publishing, execution, "
            "or enforcement remains human-gated."
        ),
        "verification": {
            "market": "pending",
            "dam": "verified",
            "user": user_state,
        },
        "tags": ["decision-receipt", "verify-action", "human-in-the-loop"],
        "timestamp": today,
    }
    body = "\n".join([
        f"# {title}",
        "",
        f"Receipt ID: {receipt.decision_id}",
        f"Receipt status: {receipt.status}",
        f"Workflow: {receipt.workflow}",
        f"Action: {receipt.decision_type}",
        f"Risk class: {receipt.risk_class}",
        f"Requester: {receipt.request.get('requester', '')}",
        f"Approver: {receipt.authority.get('approver', '')}",
        f"Approval scope: {receipt.authority.get('approval_scope', '')}",
        f"Allowed actions: {', '.join(receipt.boundary.get('allowed_actions', []))}",
        f"Denied actions: {', '.join(receipt.boundary.get('denied_actions', []))}",
        f"Context hash at check: {receipt.check.get('context_hash_at_check', '')}",
        f"Context hash at execution: {receipt.execution.get('context_hash_at_execution', '')}",
        f"Integrity hash: {receipt.receipt.get('integrity_hash', '')}",
        "",
        "## Human gate",
        "",
        "This bundle exists only after verify-action, explicit approval, seal, and explicit promote.",
        "It is evidence of bounded human authorship, not permission to auto-execute future actions.",
        "",
    ])
    content = render_frontmatter(fm) + "\n\n" + body
    path = Path(bundles_dir) / "decisions" / f"{slugify(title)}.md"

    if not approve:
        return {"approved": False, "path": str(path), "content": content}

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"approved": True, "path": str(path), "content": content}
