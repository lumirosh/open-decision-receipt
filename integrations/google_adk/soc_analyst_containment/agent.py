"""Analyst-gated synthetic endpoint-containment ADK workflow."""
from __future__ import annotations

import json
from pathlib import Path

from google.adk import Event, Workflow
from google.adk.events import RequestInput

from integrations.google_adk.governed import decide_action, prepare_action
from integrations.google_adk.models import HumanGateResponse

HERE = Path(__file__).resolve().parent


def build_workflow(*, runtime_dir: str | Path = "/tmp/odr-google-adk-soc") -> Workflow:
    runtime = Path(runtime_dir)

    def prepare_soc_review(node_input: str) -> dict:
        return prepare_action(request=json.loads(node_input), case_pack=HERE / "case-pack.yaml", receipts_dir=runtime / "receipts")

    def human_containment_decision(node_input: dict):
        packet = node_input["review_packet"]
        recommendation = packet["recommendation"]
        yield RequestInput(
            message=(
                f"Synthetic endpoint containment case {node_input['decision_id']}. Endpoint: {packet['subject_ref']}. "
                f"Recommendation: {recommendation.get('recommendation')} (confidence {recommendation.get('confidence')}); "
                f"reason: {recommendation.get('rationale')}. Missing evidence: {packet['missing_evidence'] or 'none'}. "
                f"Allowed roles: {packet['allowed_approver_roles']}. Choose approve, reject or escalate. "
                "Approval writes a local artifact only; no endpoint is contacted."
            ),
            payload=node_input,
            response_schema=HumanGateResponse,
        )

    def record_soc_decision(node_input: HumanGateResponse | dict | str) -> Event:
        response = HumanGateResponse.model_validate_json(node_input) if isinstance(node_input, str) else HumanGateResponse.model_validate(node_input)
        result = decide_action(
            **response.model_dump(), case_pack=HERE / "case-pack.yaml",
            receipts_dir=runtime / "receipts", actions_dir=runtime / "actions",
            okf_bundles_dir=runtime / "okf",
        )
        return Event(message=json.dumps(result, sort_keys=True))

    return Workflow(
        name="soc_analyst_containment_reference",
        description="Synthetic analyst-gated endpoint containment with a sealed Open Decision Receipt.",
        edges=[("START", prepare_soc_review, human_containment_decision, record_soc_decision)],
    )


root_agent = build_workflow()
