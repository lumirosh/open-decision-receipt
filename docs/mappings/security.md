# Security Weakness Mappings

A Decision Receipt does not replace security controls. It makes the authority and evidence boundary around a consequential action inspectable.

These are weakness-class mappings, not CVE assignments. A CVE identifies a disclosed vulnerability in a specific product or version. The mappings below connect recurring workflow failures to established CWE, OWASP, STRIDE, and security-control concepts.

| Weakness class | Reference | AI workflow expression | Receipt fields |
|---|---|---|---|
| Time-of-check / time-of-use | CWE-367 | Human approves one context; agent executes against a changed state | timestamps and context hashes |
| Confused deputy | CWE-441 | Agent uses tool authority for a requester who lacks it | `requester_authority`, `credential_used` |
| Broken or missing authorization | CWE-285, CWE-862 | Tool access exceeds decision authority | approval scope, allowed and denied actions |
| Privilege drift | Least-privilege failure | Agent accumulates access without a redrawn boundary | credential and tool/system record |
| Fail-open design | Insecure defaults | Reviewer or logging failure allows execution | `boundary.failure_mode` |
| Weak audit trail or repudiation | STRIDE-R | Decision cannot be reconstructed | receipt IDs, integrity hash, replayability |
| Separation-of-duties failure | SoD control failure | Same actor recommends, approves, and executes | distinct recommendation, authority, and execution roles |
| Supply-chain or context poisoning | OWASP LLM03/LLM04 | Model, retrieval corpus, or tool metadata silently shapes a decision | evidence references and context hashes |
| Excessive agency | OWASP LLM06 | Automation has broader authority than the task needs | requester authority and execution boundary |
| Business logic flaw | Application security classic | Permitted actions chain into a prohibited outcome | bounded scope and denied actions |

## Diagnostic questions

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

If a workflow cannot answer these questions, the action may be logged without its authority boundary being reconstructable.
