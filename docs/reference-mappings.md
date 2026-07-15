# Decision Receipt Reference Mappings

A Decision Receipt does not replace security controls, policy systems, or governance programs. It makes the authority and evidence basis around a consequential action inspectable.

Use this page to trace receipt fields to a security failure class, a governance framework question, or a diagnostic question that a consequential workflow should answer.

## Security weakness classes

| Weakness class | Reference | AI workflow expression | Receipt fields |
|---|---|---|---|
| Time-of-check / time-of-use | CWE-367 | Human approves one context; agent executes against a changed state | timestamps and context hashes |
| Confused deputy | CWE-441 | Agent uses tool authority for a requester who lacks it | `requester_authority`, `credential_used` |
| Broken or missing authorization | CWE-285, CWE-862 | Tool access exceeds decision authority | approval scope, allowed and denied actions |
| Privilege drift | Least-privilege failure | Agent accumulates access without a redrawn boundary | credential and tool/system record |
| Fail-open design | Insecure defaults | Reviewer or logging failure allows execution | `boundary.failure_mode` |
| Weak audit trail / repudiation | STRIDE-R | Decision cannot be reconstructed | receipt IDs, integrity hash, replayability |
| Separation-of-duties failure | SoD control failure | Same actor recommends, approves, and executes | distinct recommendation, authority, and execution roles |
| Supply-chain / context poisoning | OWASP LLM03/LLM04 | Model, RAG corpus, or tool metadata silently shapes a decision | evidence references and context hashes |
| Excessive agency | OWASP LLM06 | Automation has broader authority than the task needs | requester authority and execution boundary |
| Business logic flaw | Application security classic | Permitted actions chain into a prohibited outcome | bounded scope and denied actions |

## Framework mapping

| Framework | What it asks | What a receipt can demonstrate |
|---|---|---|
| NIST AI RMF | Accountability structures, risk evidence, enforceable controls | who had authority, what evidence existed, what control gated the action |
| EU AI Act | Record-keeping, technical documentation, human oversight | the decision path is reconstructable and the human had context, authority, and stop-power |
| India MeitY AI Governance Guidelines | Demonstrable human oversight and deployer accountability | a replayable record that a human could see, understand, stop, and own the decision |
| OWASP Top 10 for LLM Applications | Mitigations for excessive agency, injection, and poisoning | where model output crossed a trust boundary and under whose authority |

## Conformance levels

A Decision Receipt can be validated at three levels. Each level is additive: L2 implies L1; L3 implies L1 and L2.

| Level | Name | What it proves | What validates |
|---|---|---|---|
| **L1** | Documented | Required fields are present and schema-valid. The receipt is a well-formed authority object. | `dam-verify validate <receipt>` passes without schema errors |
| **L2** | Bound | Check-time and use-time context hashes are present. A reviewer can confirm whether the hashes match. | L1 + `dam-verify chain` reports `chain intact: True` |
| **L3** | Governed | The receipt is managed through a verified-action lifecycle: authority is resolved before execution, check-time and use-time are compared at seal, and a watcher reopens the receipt when its evidence or authority basis changes. | L2 + a sealed receipt reopens in `dam-verify watch` after its evidence basis changes |

The reference implementation can produce receipts at any level. Most governance workflows will operate at L2. Regulated, high-consequence workflows should target L3.

---

## Conceptual lineage

A Decision Receipt is not an isolated invention. It sits within a known line of accountability structures.

**Proof-Carrying Code (PCC).** In PCC, a program ships with a formal proof that it satisfies a stated safety policy. A verifier checks the proof independently before trusting the program. The Decision Receipt applies the same pattern to decisions instead of code: the receipt carries the evidence and authority that a verifier can inspect without trusting the original decision-maker.

**Time-of-Check to Time-of-Use (TOCTOU / CWE-367).** The canonical operating-system race condition — check a credential at time T₀, use it at T₁ when the world may have changed — maps directly to AI-assisted workflows. A human reviews evidence at check time; the system executes at use time under potentially different conditions. The receipt records both contexts so the gap becomes visible.

**Software Bill of Materials (SBOM).** An SBOM lists what went into a software artifact. A Decision Receipt lists what went into a consequential decision — evidence, authority, policy, scope, execution — and binds them to a verifiable object.

**OAuth token model.** An authorization server issues a token that a consumer can present to a resource server. The resource server trusts the token without knowing the user. A Decision Receipt is the equivalent token for a decision: it lets a party who was not present accept that an action was authorized, the same way a service accepts a signed identity assertion.

These analogies are conceptual, not conformance claims. They exist to make the receipt legible to security researchers, governance architects, and platform engineers who already work with these patterns.

## Fourteen diagnostic questions

1. What did the human check?
2. What did the system use?
3. What changed between check and use?
4. Who requested the action?
5. Did the requester have authority?
6. Whose credential or tool executed it?
7. What evidence was visible at approval time?
8. What action was actually executed?
9. Was the action within approval scope?
10. Who owns the consequence?
11. Can the decision be replayed?
12. Where does the workflow fail open?
13. Is separation of duties preserved?
14. What receipt proves all of this?

If a workflow cannot answer these, the decision was not governed. It was performed.
