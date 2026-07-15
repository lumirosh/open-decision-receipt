import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("google.adk")

from google.adk import Workflow
from google.adk.runners import InMemoryRunner
from google.genai import types

from integrations.google_adk.loan_denial.agent import build_workflow as build_loan_workflow
from integrations.google_adk.governed import decide_action, prepare_action
from integrations.google_adk.soc_analyst_containment.agent import build_workflow as build_soc_workflow


ROOT = Path(__file__).resolve().parents[1]
LOAN_PACK = ROOT / "integrations/google_adk/loan_denial/case-pack.yaml"
SOC_PACK = ROOT / "integrations/google_adk/soc_analyst_containment/case-pack.yaml"


def _prepare(tmp_path, request_file, case_pack):
    return prepare_action(
        request=json.loads(request_file.read_text()),
        case_pack=case_pack,
        receipts_dir=tmp_path / "receipts",
    )


def _request_input_response(interrupt_id, response):
    return types.Part(function_response=types.FunctionResponse(
        id=interrupt_id,
        name="adk_request_input",
        response=response,
    ))


@pytest.mark.parametrize(
    ("builder", "name", "nodes"),
    [
        (build_loan_workflow, "loan_denial_reference", {"prepare_loan_review", "human_credit_decision", "record_loan_decision"}),
        (build_soc_workflow, "soc_analyst_containment_reference", {"prepare_soc_review", "human_containment_decision", "record_soc_decision"}),
    ],
)
def test_integrations_expose_distinct_adk_graphs(tmp_path, builder, name, nodes):
    workflow = builder(runtime_dir=tmp_path)
    assert isinstance(workflow, Workflow)
    assert workflow.name == name
    actual = {
        node.name
        for edge in workflow.graph.edges
        for node in (edge.from_node, edge.to_node)
        if hasattr(node, "name")
    }
    assert nodes <= actual


@pytest.mark.parametrize(
    ("builder", "request_file", "role", "message_fragment", "expected_action"),
    [
        (build_loan_workflow, ROOT / "integrations/google_adk/loan_denial/request.json", "loan_officer", "credit", "issue_denial_notice"),
        (build_soc_workflow, ROOT / "integrations/google_adk/soc_analyst_containment/request.json", "soc_analyst", "endpoint containment", "isolate_endpoint"),
    ],
)
def test_adk_workflow_pauses_then_seals_only_a_local_artifact(
    tmp_path, builder, request_file, role, message_fragment, expected_action
):
    workflow = builder(runtime_dir=tmp_path)
    runner = InMemoryRunner(agent=workflow)

    async def exercise():
        await runner.session_service.create_session(
            app_name=runner.app_name, user_id="auditor", session_id="case"
        )
        first = []
        message = types.Content(role="user", parts=[types.Part(text=request_file.read_text())])
        async for event in runner.run_async(user_id="auditor", session_id="case", new_message=message):
            first.append(event)
        hitl = next(
            event for event in first
            if event.content and event.content.parts
            and any(part.function_call and part.function_call.name == "adk_request_input" for part in event.content.parts)
        )
        call = next(part.function_call for part in hitl.content.parts if part.function_call)
        assert message_fragment in call.args["message"].lower()
        decision_id = call.args["payload"]["decision_id"]
        response = types.Content(
            role="user",
            parts=[_request_input_response(call.id, {
                "decision_id": decision_id,
                "gate_token": call.args["payload"]["gate_token"],
                "decision": "approve",
                "approver": "synthetic_reviewer",
                "approver_role": role,
                "note": "Synthetic evidence and sample policy reviewed.",
            })],
        )
        async for _ in runner.run_async(
            user_id="auditor", session_id="case",
            invocation_id=hitl.invocation_id, new_message=response,
        ):
            pass
        await runner.close()
        return decision_id

    decision_id = asyncio.run(exercise())
    receipt = json.loads((tmp_path / "receipts" / f"{decision_id}.json").read_text())
    action = json.loads((tmp_path / "actions" / f"{decision_id}.json").read_text())
    assert receipt["status"] == "sealed"
    assert action["action"] == expected_action
    assert action["external_action_performed"] is False
    assert not (tmp_path / "okf").exists()


def test_decision_id_rejects_path_traversal_before_file_io(tmp_path):
    with pytest.raises(ValueError, match="invalid decision_id"):
        decide_action(
            decision_id="../../escaped", gate_token="invalid", decision="approve",
            approver="reviewer", approver_role="loan_officer", note="reviewed",
            case_pack=LOAN_PACK, receipts_dir=tmp_path / "receipts",
            actions_dir=tmp_path / "actions", okf_bundles_dir=tmp_path / "okf",
        )
    assert not (tmp_path.parent / "escaped.json").exists()


def test_receipt_must_belong_to_selected_workflow(tmp_path):
    prepared = _prepare(
        tmp_path,
        ROOT / "integrations/google_adk/loan_denial/request.json",
        LOAN_PACK,
    )
    with pytest.raises(ValueError, match="does not belong"):
        decide_action(
            decision_id=prepared["decision_id"], gate_token=prepared["gate_token"], decision="approve",
            approver="reviewer", approver_role="soc_analyst", note="reviewed",
            case_pack=SOC_PACK, receipts_dir=tmp_path / "receipts",
            actions_dir=tmp_path / "actions", okf_bundles_dir=tmp_path / "okf",
        )


@pytest.mark.parametrize(("decision", "status"), [("reject", "denied"), ("escalate", "escalated")])
def test_non_approval_decisions_record_their_time(tmp_path, decision, status):
    prepared = _prepare(
        tmp_path,
        ROOT / "integrations/google_adk/loan_denial/request.json",
        LOAN_PACK,
    )
    result = decide_action(
        decision_id=prepared["decision_id"], gate_token=prepared["gate_token"], decision=decision,
        approver="reviewer", approver_role="loan_officer", note="reviewed",
        case_pack=LOAN_PACK, receipts_dir=tmp_path / "receipts",
        actions_dir=tmp_path / "actions", okf_bundles_dir=tmp_path / "okf",
    )
    receipt = json.loads(Path(result["receipt_path"]).read_text())
    assert receipt["status"] == status
    assert receipt["authority"]["decided_at"]


def test_failed_local_action_write_does_not_seal_receipt(tmp_path):
    prepared = _prepare(
        tmp_path,
        ROOT / "integrations/google_adk/loan_denial/request.json",
        LOAN_PACK,
    )
    original_write_text = Path.write_text

    def fail_action_write(path, *args, **kwargs):
        if path.parent.name == "actions":
            raise OSError("disk full")
        return original_write_text(path, *args, **kwargs)

    with patch("pathlib.Path.write_text", new=fail_action_write):
        with pytest.raises(OSError, match="disk full"):
            decide_action(
                decision_id=prepared["decision_id"], gate_token=prepared["gate_token"], decision="approve",
                approver="reviewer", approver_role="loan_officer", note="reviewed",
                case_pack=LOAN_PACK, receipts_dir=tmp_path / "receipts",
                actions_dir=tmp_path / "actions", okf_bundles_dir=tmp_path / "okf",
            )
    receipt = json.loads((tmp_path / "receipts" / f"{prepared['decision_id']}.json").read_text())
    assert receipt["status"] == "needs_human_review"


def test_linear_examples_do_not_advertise_unimplemented_evidence_continuation():
    for case_pack in (LOAN_PACK, SOC_PACK):
        assert "request_more_evidence" not in case_pack.read_text()


def test_response_is_bound_to_the_specific_displayed_gate(tmp_path):
    request_file = ROOT / "integrations/google_adk/loan_denial/request.json"
    first = _prepare(tmp_path, request_file, LOAN_PACK)
    second = _prepare(tmp_path, request_file, LOAN_PACK)
    with pytest.raises(ValueError, match="gate token"):
        decide_action(
            decision_id=second["decision_id"], gate_token=first["gate_token"],
            decision="approve", approver="reviewer", approver_role="loan_officer",
            note="reviewed", case_pack=LOAN_PACK,
            receipts_dir=tmp_path / "receipts", actions_dir=tmp_path / "actions",
            okf_bundles_dir=tmp_path / "okf",
        )
