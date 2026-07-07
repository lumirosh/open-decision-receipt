# Decision Receipt Lifecycle

The schema defines the receipt. The lifecycle explains why it exists.

A Decision Receipt is not only a record written after an AI-assisted action. It is the decision's authority object across four tenses:

```text
before      authority is checked and scoped
during      execution is bounded
after       the action is sealed as replayable evidence
over time   the receipt reopens if its basis changes
```

## Why this matters

Most human-in-the-loop systems prove only that a human was present.

Presence is weak. It does not prove:

- what the human checked
- what evidence was visible
- what authority the human actually had
- what action the system executed
- whether the world changed between approval and execution
- who owns the consequence

A Decision Receipt proves authorship, not presence.

```text
Human-in-the-loop = a human was there.
Decision Receipt = a human signed scoped authority into a replayable object.
```

## State machine

```text
DRAFT
  ↓
VERIFY ACTION
  ↓
UNKNOWN / DENIED / NEEDS_HUMAN_REVIEW / AUTHORIZED
  ↓
APPROVE
  ↓
AUTHORIZED
  ↓
SEAL
  ↓
SEALED / REOPENED
  ↓
WATCH
  ↓
REOPENED if the basis drifts
  ↓
PROMOTE
  ↓
verified OKF/DAM knowledge
```

## States

| State | Meaning |
|---|---|
| `draft` | Receipt object exists but authority has not been resolved |
| `unknown` | No authority bundle or evidence basis exists. Fail closed |
| `denied` | Actor/action/risk class is outside the allowed set |
| `needs_human_review` | The action can continue only if a human signs scoped authority |
| `authorized` | Authority has been signed or policy-authorized |
| `sealed` | Execution matched check-time basis and the receipt has an integrity hash |
| `reopened` | The basis changed or TOCTOU was detected. Re-verification required |
| `revoked` | Human or policy withdrew the authority |

## Core verbs

### 1. `verify_action`

Checks the requested action before execution.

Inputs:

```text
actor
workflow
action
risk_class
context_refs
params
```

Reads:

```text
OKF authority bundle
required evidence
allowed actions
denied actions
human review rule
```

Returns:

```text
unknown
denied
needs_human_review
authorized
```

### 2. `approve`

The human signs scoped authority into the receipt.

Adds:

```text
approver
approval_method
approved_at
authority_basis
approval_scope
separation_of_duties_ok
```

This is the main philosophical point. The human is not rubber-stamping output. The human is authoring the allowed scope.

### 3. `seal`

Runs after execution.

It recomputes the evidence basis and compares:

```text
context_hash_at_check
context_hash_at_execution
```

If they match:

```text
status = sealed
integrity_hash = sha256(canonical_receipt)
```

If they differ:

```text
status = reopened
finding = TOCTOU: context changed between check and use
```

### 4. `watch`

Runs after sealing.

If a sealed receipt depends on an evidence source that later changes, the receipt reopens.

```text
sealed proof → reopened question
```

This is what makes the receipt more than an audit record. It knows when it has stopped being sufficient proof.

### 5. `promote`

Turns a sealed receipt into verified OKF/DAM knowledge.

Default is dry-run:

```text
user: pending
state: verified_draft
```

With explicit approval:

```text
user: approved
state: verified
```

Promotion is not execution permission. It is knowledge promotion. Reuse, publishing, or enforcement remains human-gated.

## One concrete example

A release workflow wants to deploy a certified workflow.

```text
actor: release_workflow
workflow: cert_gated_deployment
action: deploy_certified_workflow
risk_class: high
context_refs: certification_status
```

The authority bundle says:

```text
release_workflow may deploy_certified_workflow
release_workflow may not modify_certification or bypass_gate
high risk requires human approval
certification_status is required evidence
failure mode is fail closed
```

Flow:

```text
verify_action → needs_human_review
approve       → authorized
seal          → sealed
watch         → reopened if certification_status changes
promote       → OKF bundle only after explicit approval
```

The demo line:

```text
Same actor, same action, same workflow.
Valid yesterday, blocked today, and the receipt explains why.
```

## What this solves

| Failure | How the lifecycle exposes it |
|---|---|
| Rubber-stamp approval | `authority.approver`, `approval_scope`, and evidence seen are explicit |
| Confused deputy | `requester_authority` and execution credential can be compared |
| Broken authorization | action must be in `allowed_actions`, not in `denied_actions` |
| TOCTOU | check-time hash and execution-time hash must match |
| Fail-open workflow | `boundary.failure_mode` is explicit |
| Weak audit trail | receipt carries IDs, hashes, evidence, and replay fields |
| Stale proof | watcher reopens sealed receipts when basis changes |
| Governance theatre | promotion requires explicit human approval |

## The invariant

```text
No consequential AI-enabled action should happen without replayable proof of evidence, authority, scope, execution, and accountability.
```
