# Signal Map

This project came from one converging pattern: AI systems are creating accountability without matching authority.

The Decision Receipt is the object that closes that gap.

## Core thesis

AI does not remove old security problems. It moves them into business workflows.

Classic failures now appear inside AI-assisted decisions:

```text
TOCTOU
confused deputy
broken authorization
privilege drift
fail-open workflow
weak audit trail
separation-of-duties failure
context poisoning
excessive agency
business logic flaws
```

The receipt names these failures at the decision layer.

## Signal 1: the market wound

The public wound is simple:

```text
The human is accountable, but the system did not give them real authority.
```

Most AI governance language says "keep a human in the loop." That is not enough.

The real questions are:

```text
What did the human see?
What could they stop?
What were they allowed to approve?
What did the system actually do?
What changed between approval and execution?
What proves all of this later?
```

This is why the receipt starts with authority, not logging.

## Signal 2: governance and compliance records

Governance and regulatory work already asks for the receipt shape:

```text
developer supplied fields
deployer supplied fields
reviewer decision
reviewer justification
training and qualification
source evidence
record-keeping
human review
```

The compliance world is asking:

```text
Can you prove meaningful human review happened?
```

The Decision Receipt answer is:

```text
Only if the review is bound to evidence, authority, scope, execution, and replayability.
```

Governance records are the after-tense. They prove what was reviewed. The receipt adds check-time vs use-time, boundaries, integrity, and reopening.

## Signal 3: structured outputs and allowed actions

Control-layer work asks a different question:

```text
Can unauthorized actions be made ungenerable?
```

That is useful, but the allowed set has to come from somewhere.

The receipt supplies that object:

```text
boundary.allowed_actions
boundary.denied_actions
authority.approval_scope
authority.authority_basis
check.evidence_seen
```

Structured outputs can consume the allowed set. The receipt explains why that allowed set exists.

## Signal 4: runtime enforcement

Runtime boundaries can enforce a verdict:

```text
no valid receipt → no execution
authorized receipt → action may proceed within scope
reopened receipt → stop and re-verify
```

The receipt is not a runtime engine. It is the authority object the runtime engine can consume.

## Signal 5: drift

Most records assume the world stays still.

AI workflows do not.

A policy changes. A certification is revoked. A source document updates. A risk score changes. A reviewer loses authority. A model version changes.

A sealed receipt must be able to become a question again.

```text
sealed → reopened
```

That is why the lifecycle includes `watch`.

## Signal 6: DAM and OKF

OKF is the verified knowledge file.

DAM is the lifecycle engine around it.

```text
OKF bundle = authority source
DAM verify_action = action check
Decision Receipt = portable proof object
DAM promote = human-approved movement into verified knowledge
```

The receipt does not replace policies, runbooks, or governance records. It binds them to the action.

## The convergence

Each signal sees one part of the same object:

| Signal | What it sees | Receipt tense |
|---|---|---|
| Market wound | accountability without authority | why the object exists |
| Governance record | meaningful human review | after |
| Structured outputs | allowed actions before generation | before |
| Runtime boundary | execution must consume a verdict | during |
| Drift | proof can become stale | over time |
| OKF/DAM | verified knowledge needs human promotion | lifecycle |

## Final compression

```text
Logs look backward.
Guardrails look sideways.
The receipt looks across the whole decision.
```

Or shorter:

```text
The Decision Receipt is a warrant, not a wrapper.
```
