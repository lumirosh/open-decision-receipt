"""Decision Receipt - the object and its lifecycle.

Mirrors the public schema (lumirosh/open-decision-receipt) and adds the
lifecycle status. A receipt is a state machine, not a document:

    DRAFT -> AUTHORIZED -> SEALED -> REOPENED -> (re-verify)
       |          |                    ^
       |          +-- seal-time drift  |
       +-- DENIED / ESCALATED / NEEDS_HUMAN_REVIEW
                              watcher detects basis drift
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_of(obj) -> str:
    """Return a full SHA-256 digest for durable integrity evidence."""
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


# Lifecycle states
DRAFT = "draft"
AUTHORIZED = "authorized"
DENIED = "denied"
ESCALATED = "escalated"
NEEDS_HUMAN_REVIEW = "needs_human_review"
UNKNOWN = "unknown"
SEALED = "sealed"
REOPENED = "reopened"
REVOKED = "revoked"

TERMINAL_NEGATIVE = {DENIED, ESCALATED, REVOKED}


@dataclass
class Receipt:
    decision_id: str
    workflow: str
    decision_type: str
    risk_class: str
    status: str = DRAFT

    request: dict = field(default_factory=dict)
    check: dict = field(default_factory=dict)
    recommendation: dict = field(default_factory=dict)
    authority: dict = field(default_factory=dict)
    execution: dict = field(default_factory=dict)
    boundary: dict = field(default_factory=dict)
    accountability: dict = field(default_factory=dict)
    receipt: dict = field(default_factory=dict)

    findings: list = field(default_factory=list)

    def flag(self, finding: str) -> None:
        self.findings.append({"at": now_iso(), "finding": finding})

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def replayable(self) -> bool:
        return bool(self.receipt.get("integrity_hash")) and self.status == SEALED

    def seal_hash(self) -> str:
        body = self.to_dict()
        body["receipt"] = {k: v for k, v in body["receipt"].items() if k != "integrity_hash"}
        return sha256_of(body)
