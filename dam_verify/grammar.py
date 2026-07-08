"""Compile authorized Decision Receipts into constrained action schemas.

The BEFORE tense becomes enforceable at generation time: the model can only
emit actions inside the approved scope and must bind the output to the
Decision Receipt that granted authority.
"""
from __future__ import annotations

from .receipt import AUTHORIZED, SEALED, Receipt


SCHEMA_ALLOWED_STATUSES = {AUTHORIZED, SEALED}


def compile_action_schema(receipt: Receipt, param_schema: dict | None = None) -> dict:
    """Return a JSON Schema constrained by a receipt's authority boundary.

    AUTHORIZED receipts support pre-execution grammar generation. SEALED receipts
    support later replay/demo generation from the same authority boundary. Any
    other status fails closed.
    """
    if receipt.status not in SCHEMA_ALLOWED_STATUSES:
        raise ValueError(
            f"receipt {receipt.decision_id} is '{receipt.status}', not authorized or sealed - "
            "no grammar without authority"
        )
    if not receipt.authority:
        raise ValueError(f"receipt {receipt.decision_id} has no authority block - no grammar")

    allowed = list(receipt.boundary.get("allowed_actions", []))
    scope = receipt.authority.get("approval_scope")
    actions = [scope] if scope in allowed else allowed
    if not actions:
        raise ValueError("empty allowed set - nothing may be generated")

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"scoped-actions:{receipt.decision_id}",
        "type": "object",
        "additionalProperties": False,
        "required": ["action", "decision_id"],
        "properties": {
            "action": {"enum": actions},
            "decision_id": {"const": receipt.decision_id},
            "params": param_schema or {
                "type": "object",
                "const": receipt.request.get("params", {}),
            },
        },
    }
