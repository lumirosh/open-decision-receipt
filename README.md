# The Open Decision Receipt Schema

**Human-in-the-loop is not evidence. A Decision Receipt is.**

An open, vendor-neutral schema for proving that AI-enabled decisions were **authorized, evidenced, bounded, executed as approved, accountable, and replayable**.

---

## The problem

Firewalls, IAM, and network controls protect Layers 1-7. AI agents don't attack there. They operate at:

- **Layer 8 - human judgment under pressure:** approval fatigue, urgency injection, rubber-stamping, "the dashboard said it was okay."
- **Layer 9 - organizational authority:** unclear ownership, compliance that performs instead of prevents, accountability without stop-power.

AI is not mainly creating new vulnerabilities. It is resurfacing **old, well-known security weakness classes** inside AI-enabled business workflows - faster, quieter, and harder to see:

| Weakness class | Reference | AI workflow expression |
|---|---|---|
| Time-of-check / time-of-use (TOCTOU) | CWE-367 | A human approves one context; the agent executes later against a changed state |
| Confused deputy | CWE-441 | An agent uses its tool-level authority on behalf of a requester who lacks that authority |
| Broken / missing authorization | CWE-285, CWE-862 | Tool access exceeds decision authority; approval is granted at workflow level, not action level |
| Privilege drift | Least-privilege failure | The agent accumulates CRM, email, billing, database access; nobody redraws the trust boundary |
| Fail-open design | Insecure defaults | Reviewer unavailable → approval passes; logs fail → execution continues |
| Weak audit trail / repudiation | STRIDE-R, logging failure | No prompt record, no model version, no rationale - the decision cannot be reconstructed |
| Separation-of-duties failure | SoD control failure | The same agent recommends, executes, and summarizes its own action |
| Supply-chain / context poisoning | OWASP LLM03/LLM04 | Vendor models, RAG corpora, and tool metadata silently shape decisions |
| Excessive agency | OWASP LLM06 | Autonomy and permissions far beyond what the task requires |
| Business logic flaw | AppSec classic | Individually permitted actions chain into a prohibited outcome |

Every one of these classes has a decades-old name. What's new is the execution surface.

## The missing artifact

When an AI-assisted decision goes wrong, organizations discover they have **fragments** - a Slack message, a workflow log, a model output, a dashboard screenshot - but no **decision object**.

A log says: *something happened.*

A **Decision Receipt** says: *this happened because this authority approved this bounded action, using this evidence, under this policy, at this time - with this access path, this execution boundary, and this accountable owner.*

| Audit log | Decision Receipt |
|---|---|
| Records events | Records judgment |
| System-centered | Authority-centered |
| Shows what happened | Shows why it was allowed |
| Timestamp only | Check-time **and** use-time |
| Good for debugging | Good for accountability |

The receipt binds **check-time to use-time**. Every receipt carries `checked_at` / `executed_at` and `context_hash_at_check` / `context_hash_at_execution`. If the hashes differ, you have found a TOCTOU gap between what the human approved and what the machine did.

## The schema

The minimum schema is in [`decision-receipt.schema.yaml`](./decision-receipt.schema.yaml). A worked example is in [`examples/`](./examples/).

Eight blocks:

```text
request        who asked, with what authority
check          what was verified, when, against what evidence
recommendation what the model/human suggested, and dissenting signals
authority      who approved, on what basis, within what scope
execution      what actually ran, with which credential, against which state
boundary       allowed vs denied actions; fail-open or fail-closed
accountability who owns the consequence; escalation path
receipt        replayability: prompt, output, run IDs, integrity hash
```

Each field exists to expose a specific weakness class:

| Weakness | Receipt field that exposes it |
|---|---|
| TOCTOU (CWE-367) | `checked_at` vs `executed_at`, context hashes |
| Confused deputy (CWE-441) | `requester_authority` vs `credential_used` |
| Broken authorization | `approval_scope`, `allowed_actions` / `denied_actions` |
| Privilege drift | `credential_used`, `tool_or_system` |
| Fail-open | `boundary.failure_mode` |
| Repudiation | `receipt.*` IDs, `integrity_hash`, `replayable` |
| SoD failure | distinct `recommended_by` / `approver` / `executed_by` |
| Missing revocation | `authority_basis`, approval timestamps vs policy version |

## Regulatory mapping

These frameworks ask for oversight and record-keeping. The receipt is the artifact that demonstrates it rather than documents it.

| Framework | What it asks | What the receipt proves |
|---|---|---|
| **NIST AI RMF** (Govern / Map / Measure / Manage) | Accountability structures, risk evidence, enforceable controls | Who had authority, what evidence existed, what control actually gated the action |
| **EU AI Act** | Record-keeping/logging, technical documentation, human oversight | The decision path can be reconstructed; the human had context, authority, and stop-power |
| **India MeitY AI Governance Guidelines (7 Sutras)** | Human oversight that is demonstrated, not documented; deployer accountability | A live, replayable record that a human could see, understand, stop, and own the decision |
| **OWASP Top 10 for LLM Applications** | Mitigations for excessive agency, injection, poisoning | Where model output crossed a trust boundary and under whose authority |

The question regulators are converging on is the question this schema answers:

> **What did the human check? What did the system use? What changed in between?**

## Fourteen diagnostic questions

For any AI-enabled workflow:

1. What did the human check?
2. What did the system use?
3. What changed between check and use?
4. Who requested the action?
5. Did the requester have authority?
6. Whose credential/tool executed it?
7. What evidence was visible at approval time?
8. What action was actually executed?
9. Was the action within approval scope?
10. Who owns the consequence?
11. Can the decision be replayed?
12. Where does the workflow fail open?
13. Is separation of duties preserved?
14. What receipt proves all of this?

If a workflow cannot answer these, the decision was not governed - it was performed.

## Design invariant

```text
No consequential AI-enabled action should happen without replayable proof of
evidence, authority, scope, execution, and accountability.
```

## Contributing

Issues and PRs welcome. See [CONTRIBUTING.md](./CONTRIBUTING.md). Good contributions map fields to named weakness classes, add worked examples from real workflow types, or improve regulatory mappings with primary-source references. Unverifiable incident claims will not be merged; every example needs a reproducible or primary-sourced basis.

## License

Apache-2.0. Use it, implement it, ship it.

---

*Maintained by [LumiRosh Research](https://lumirosh.com). To see how this schema maps to your workflows: [lumirosh.com](https://lumirosh.com).*
