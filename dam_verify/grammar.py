"""Compile authorized Decision Receipts into constrained action schemas.

A host can use the schema to constrain generation to an approved action and
its Decision Receipt. The schema itself does not authenticate authority or
enforce runtime execution.
"""
from __future__ import annotations

from .engine import canonical_action
from .receipt import AUTHORIZED, SEALED, Receipt, sha256_of


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
    if not isinstance(scope, str) or not scope or scope not in allowed or scope != receipt.decision_type or scope != receipt.request.get("requested_action"):
        raise ValueError("approval scope does not bind the requested action")
    action = canonical_action(receipt.workflow, scope, receipt.request.get("params"))
    digest = sha256_of(action)
    if (action != receipt.request.get("canonical_action")
            or digest != receipt.request.get("action_hash") or digest != receipt.authority.get("action_hash")):
        raise ValueError("action commitment is missing or changed")
    params = {"type": "object", "const": action["parameters"]}
    if param_schema is not None:
        params = {"allOf": [params, param_schema]}

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"scoped-actions:{receipt.decision_id}",
        "type": "object",
        "additionalProperties": False,
        "required": ["action", "decision_id", "params"],
        "properties": {
            "action": {"enum": [scope]},
            "decision_id": {"const": receipt.decision_id},
            "params": params,
        },
    }
