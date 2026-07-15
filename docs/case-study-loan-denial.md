# Case Study: AI-Assisted Loan Denial

> An underwriter declines a loan application. Six months later the applicant disputes the decision. The bank must prove what was checked, who had authority, and that nothing changed between review and execution. Without a receipt, all they have is a model output, a click log, and a denial letter.

Illustrative only. This worked example shows how a high-risk credit decision can remain replayable without treating a human click as sufficient evidence.

Source object: [`../examples/loan-denial-receipt.yaml`](../examples/loan-denial-receipt.yaml).

## The scenario

A credit-scoring model recommends denial for an application. A loan officer reviews the evidence. A lending manager, who has delegated authority for this risk class, approves the bounded denial. The workflow issues the notice only when the execution context still matches the reviewed context.

Without a receipt, a later reviewer may find fragments: a model output, an approval click, and a denial notice. They cannot reliably establish what the reviewer saw, who had authority, or whether the application changed before the notice was issued.

## Producer and consumer flow

```mermaid
sequenceDiagram
    participant Applicant
    participant Model as Credit model
    participant Officer as Loan officer
    participant Manager as Lending manager
    participant Receipt as Decision Receipt
    participant Workflow as Lending workflow
    participant Auditor as Auditor or regulator

    Applicant->>Model: Submit application LN-88213
    Model->>Receipt: Produce recommendation and draft receipt
    Note over Receipt: Check-time evidence is captured:<br/>application, credit report, income verification, policy
    Receipt->>Officer: Require independent human review
    Officer->>Receipt: Record reviewed evidence and dissenting signal
    Receipt->>Manager: Request scoped denial approval
    Manager->>Receipt: Approve denial under authority matrix v4 L2
    Receipt->>Workflow: Permit only the approved denial action
    Workflow->>Receipt: Seal if execution context equals check-time context
    Receipt-->>Applicant: Issue denial notice with reason code

    Auditor->>Receipt: Replay six months later
    Receipt-->>Auditor: Show evidence, reviewer, approver, scope,<br/>execution result, and intact check-to-use context
```

## What the receipt proves

| Question | Receipt evidence |
|---|---|
| What did the AI recommend? | `recommendation` block, model version, confidence, rationale |
| What did the human actually check? | `check.evidence_seen`, assumptions, and dissenting signals |
| Who had authority to approve denial? | `authority.approver`, `authority_basis`, and approval scope |
| Was separation of duties preserved? | Model recommends, officer reviews, manager approves, workflow executes |
| What did the system execute? | `execution.actual_action`, system, credential, result |
| Did anything change before execution? | `context_hash_at_check` equals `context_hash_at_execution` |
| Who owns the consequence and appeal route? | `accountability` block |

## Why this is different from human presence

```text
Human-in-the-loop: a person clicked approval.

Decision Receipt: a named authority approved one bounded action after a
separate reviewer recorded evidence, and the workflow proved it executed
against the same context.
```

## Structured evidence

The loan-denial receipt mixes plain evidence labels with a `structured_query` item for the income-verification conclusion. It records a parameterized query, source snapshot, engine version, canonicalization method, and a hash commitment to a protected result artifact. That makes the evidence provenance inspectable without embedding applicant documents in a public example.

The reference implementation does not re-run that query. See [`future-directions.md`](./future-directions.md) for the boundary and a future re-verification path.

## Compare the worked examples

- [`loan-denial-receipt.yaml`](../examples/loan-denial-receipt.yaml): working-as-intended, replayable high-risk denial.
- [`case-study-soc-containment.md`](./case-study-soc-containment.md): policy-authorized, reversible SOC containment that reopens when its threat-intel basis changes.
- [`claim-payout-receipt.yaml`](../examples/claim-payout-receipt.yaml): detects a context change between check and use.
- [`gift-card-fraud-no-receipt.yaml`](../examples/gift-card-fraud-no-receipt.yaml): shows the failure mode when no receipt exists.
