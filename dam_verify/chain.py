"""Tamper-evident hash chain over sealed Decision Receipts.

Each chain entry binds the receipt's integrity hash to the previous entry's
chained hash. Editing any historical chain entry breaks that entry and every
link after it.

This is not a signature scheme. It is an intentionally small tamper-evidence
layer for the reference implementation.
"""
from __future__ import annotations

import json
from pathlib import Path

from .receipt import sha256_of

GENESIS = "sha256:genesis"


class ReceiptChain:
    def __init__(self, root: Path):
        self.path = Path(root) / "chain.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def has(self, decision_id: str) -> bool:
        return any(entry["decision_id"] == decision_id for entry in self._entries())

    def head(self) -> str:
        entries = self._entries()
        return entries[-1]["chained_hash"] if entries else GENESIS

    def append(self, decision_id: str, integrity_hash: str) -> dict:
        entry = {
            "n": len(self._entries()),
            "decision_id": decision_id,
            "integrity_hash": integrity_hash,
            "prev": self.head(),
        }
        entry["chained_hash"] = sha256_of(entry)
        with self.path.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")
        return entry

    def verify(self) -> tuple[bool, int | None]:
        """Return (ok, first_broken_index)."""
        prev = GENESIS
        for entry in self._entries():
            expected = sha256_of({key: entry[key] for key in ("n", "decision_id", "integrity_hash", "prev")})
            if entry["prev"] != prev or entry["chained_hash"] != expected:
                return False, entry["n"]
            prev = entry["chained_hash"]
        return True, None
