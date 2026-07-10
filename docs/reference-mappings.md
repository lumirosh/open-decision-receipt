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
