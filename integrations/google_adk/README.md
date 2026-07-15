# Google ADK Integration

Two synthetic Google ADK workflows demonstrate how Open Decision Receipt fits inside an executable human-in-the-loop application. The receipt core remains vendor-neutral; Google ADK is only the orchestration adapter.

## Install

From the repository root:

```bash
python -m venv .venv-adk
.venv-adk/bin/python -m pip install -e '.[adk,dev]'
```

## Loan denial

```bash
.venv-adk/bin/adk run integrations/google_adk/loan_denial
```

Paste `integrations/google_adk/loan_denial/request.json`. ADK verifies the sample evidence and policy, pauses for a loan officer or lending manager, and writes only local synthetic artifacts under `/tmp/odr-google-adk-loan/`.

## SOC analyst-gated containment

```bash
.venv-adk/bin/adk run integrations/google_adk/soc_analyst_containment
```

Paste `integrations/google_adk/soc_analyst_containment/request.json`. ADK pauses for a SOC analyst or incident commander. Approval records a local mock isolation only; it contacts no endpoint.

This is deliberately different from the existing [policy-authorized SOC case](../../docs/case-study-soc-containment.md):

```text
Analyst-gated example: recommendation → inline analyst approval → local mock action
Policy-authorized example: narrow reversible action → post-action ownership → watch and reopen on drift
```

## Human response

Copy the `decision_id` shown by ADK:

```json
{
  "decision_id": "DR-...",
  "gate_token": "copy the token from the displayed ADK payload",
  "decision": "approve",
  "approver": "synthetic_reviewer",
  "approver_role": "loan_officer",
  "note": "Synthetic evidence and sample policy reviewed."
}
```

Valid decisions are `approve`, `reject`, and `escalate`. Evidence continuation is intentionally not advertised by these linear examples; a production workflow must collect new evidence, re-verify it, and open a new bound review. Demo identities and roles are declared strings, not authenticated credentials.

## Boundary

These examples prove orchestration and receipt lifecycle behavior. They are not production lending or endpoint-security applications. A customer must replace sample policy, evidence, identity binding, authority, action connectors, compliance controls, monitoring, rollback, and UI inside its own environment.

The included JSON file store is a single-user demonstration without transactional locking. Concurrent deployments must use a transactional receipt store. Production human gates must bind the displayed receipt, authenticated session, verified role, and signed decision rather than trusting the declared identity strings used here.

Promotion remains a separate dry-run preview. No workflow automatically writes reusable verified knowledge.

## Test

```bash
.venv-adk/bin/python -m pytest -q tests/test_google_adk_integration.py
```
