# MCP Verified Action Bridge

Status: concept note for implementers

## One-line thesis

MCP says what an agent can call. A Decision Receipt says what the agent can justify.

## Why this matters

MCP exposes tools to agents. That is capability plumbing.

High-risk workflows also need authority plumbing:

- why this action is legitimate
- who is accountable
- who actually has authority
- what evidence exists before action
- what boundary applies
- whether the decision can be replayed later

A tool call is not proof of authorization. An execution log is not proof of authorization.

The missing object is the verified action object: a Decision Receipt shaped before or around action, grounded in a trusted source of workflow, policy, evidence, and authority rules.

## Architecture

```text
Proposed agent or tool action
  -> workflow context captured
  -> verified source-of-truth lookup
  -> authority and accountability check
  -> boundary evaluation
  -> verdict: allow / block / needs_human_review / unknown
  -> Decision Receipt generated
  -> runtime boundary can consume the verdict
```

Plain version:

```text
MCP exposes action.
Source of truth provides evidence.
Verification checks authority.
Receipt records the decision.
Runtime boundary enforces downstream.
```

## What this is not

This is not a claim that a receipt replaces runtime controls.

The clean split:

```text
Runtime controls decide what can execute.
Decision Receipts preserve why execution was allowed, denied, or escalated.
```

In production, a runtime boundary may use the receipt verdict as one input. The receipt itself is not a firewall.

## Minimal verification result

A verification layer sitting before an MCP tool call can return a small verdict object:

```json
{
  "verdict": "needs_human_review",
  "reason": "authority basis changed after original approval",
  "authority_basis": "missing_reverification",
  "evidence": [
    "source://policy/high-risk-human-oversight",
    "source://workflow/current-approval-state"
  ],
  "missing": [
    "new approver",
    "updated evidence basis",
    "post-change acceptance"
  ],
  "receipt": "receipts/DR-YYYY-MM-DD-001.yaml",
  "runtime_boundary_hint": "block until re-approved"
}
```

## Example scenario

A workflow was valid at T0.

At T1, the evidence basis changes. A certification breaks, a policy changes, a customer state changes, a risk score expires, or an approval scope no longer matches the action.

An agent later tries to proceed using the old state.

The verification layer checks the trusted source of truth and returns:

```text
No. The authority basis changed.
This action needs re-verification before execution.
```

The receipt records why.

The real question is not only:

```text
Can the system execute?
```

It is:

```text
Is this action still authorized?
```

## Field mapping

| Question | Receipt block |
|---|---|
| What is being requested? | `request` |
| What evidence was checked? | `check` |
| Who or what recommended the action? | `recommendation` |
| Who had authority to approve it? | `authority` |
| What actually executed? | `execution` |
| What should have been allowed or denied? | `boundary` |
| Who owns the consequence? | `accountability` |
| Can the decision be replayed? | `receipt` |

## Design guardrails

Do not claim:

- receipts replace runtime enforcement
- logs prove authorization
- tool availability equals authority
- human-in-the-loop equals verified oversight

Do claim:

- MCP describes capability
- a receipt describes authority around capability
- high-risk action needs evidence, scope, boundary, execution, and accountability
- runtime controls can consume verified action verdicts

## Canonical lines

```text
MCP says what the agent can call. A Decision Receipt says what the agent can justify.
```

```text
MCP is capability plumbing. Decision Receipt is authority plumbing.
```

```text
Execution logs prove that something happened. Decision Receipts prove why it was allowed.
```

```text
A receipt is not the runtime boundary. It is the verified action object a boundary can enforce against.
```
