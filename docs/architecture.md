# Open Decision Receipt Architecture

A Decision Receipt is the portable authority and evidence object around a consequential AI-enabled action. It does not replace a runtime control. It makes the basis for an allow, block, or escalation inspectable and replayable.

## 30-second flow

```mermaid
flowchart LR
    A[AI or agent proposes an action] --> B[Evidence and policy checked]
    B --> C{Authority resolved?}
    C -->|No basis| D[Unknown or denied]
    C -->|Human review needed| E[Human signs scoped authority]
    C -->|Policy-authorized| F[Authorized]
    E --> F
    F --> G[Workflow executes bounded action]
    G --> H{Check context equals use context?}
    H -->|Yes| I[Seal replayable receipt]
    H -->|No| J[Reopen for re-verification]
    I --> K[Watch for later basis drift]
    K -->|Basis changed| J
```

## Who does what

```mermaid
flowchart TB
    Model[AI model or agent<br/>recommends] --> Officer[Human reviewer<br/>checks evidence and dissent]
    Officer --> Approver[Authorized approver<br/>signs bounded authority]
    Approver --> Workflow[Workflow or runtime boundary<br/>executes only allowed action]
    Workflow --> Receipt[Decision Receipt<br/>records evidence, authority, scope, execution]
    Receipt --> Auditor[Auditor, regulator, or downstream control<br/>replays why action was allowed]
```

The receipt preserves separation of duties when recommendation, review, approval, and execution are distinct roles.

## Lifecycle and boundary

```text
Before action:  verify evidence, policy, requester authority, and scope.
During action:  enforce the approved boundary in the workflow or runtime layer.
After action:   seal when check-time and execution-time context match.
Over time:      watch for evidence or authority drift and reopen when needed.
Later:          replay the receipt to reconstruct why the action was allowed.
```

## MCP and verified action

```mermaid
flowchart LR
    Tool[MCP tool call] --> Context[Workflow context]
    Context --> Source[Verified source of truth]
    Source --> Verify[Authority and evidence check]
    Verify --> Verdict{Verdict}
    Verdict -->|Authorized| Receipt[Decision Receipt]
    Verdict -->|Needs human review| Gate[Human gate]
    Verdict -->|Denied or unknown| Block[Do not execute]
    Gate --> Receipt
    Receipt --> Runtime[Runtime boundary can consume verdict]
```

MCP describes what an agent can call. A Decision Receipt describes what the agent can justify. For implementation detail, see [`mcp-verified-action-bridge.md`](./mcp-verified-action-bridge.md).

## Worked example

See the full producer-to-consumer flow in [`case-study-loan-denial.md`](./case-study-loan-denial.md):

```text
model recommendation
→ human evidence review
→ manager approval
→ bounded workflow execution
→ replay six months later
```

## Documentation map

| Need | Document |
|---|---|
| See one high-risk decision end to end | [`case-study-loan-denial.md`](./case-study-loan-denial.md) |
| Understand object states and lifecycle verbs | [`lifecycle.md`](./lifecycle.md) |
| Connect receipts to MCP tool-use boundaries | [`mcp-verified-action-bridge.md`](./mcp-verified-action-bridge.md) |
| Review weakness classes and framework mappings | [`reference-mappings.md`](./reference-mappings.md) |
| Run the reference CLI | [`quickstart.md`](./quickstart.md) |
| Understand explicit non-claims | [`limitations.md`](./limitations.md) |
