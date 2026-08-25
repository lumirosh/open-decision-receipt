# Security Weakness Mappings

A Decision Receipt does not replace security controls. It makes the authority and evidence boundary around a consequential action inspectable.

## Verifier-bound receipt interpretation

A Decision Receipt carries assertions, evidence references, and lifecycle state. Receipt integrity or schema conformance does not by itself establish the authorization, completeness, correctness, or independent truth of every claim it contains. A consequential conclusion requires a claim-appropriate verifier whose result remains bounded to its scope, binding, freshness, evaluation context, dependencies, and explicit non-claims. The relying-party decision remains separate.

```text
SECURITY CLAIM
      ↓ carried by
RECEIPT / TOKEN / RECORD / ATTESTATION
      ↓ evaluated by
CLAIM-APPROPRIATE VERIFIER
      ↓ produces
BOUNDED ACCEPTED RESULT
      ↓ consumed under policy by
RELYING-PARTY DECISION
```

Two negative cases must remain explicit when integrations begin consuming external verifier results:

- **Signed-receipt overclaim:** valid receipt integrity must not imply that execution was authorized without the relevant verifier result.
- **Transitive failure laundering:** a raw successful delegation or execution result must not hide a failed, stale, missing, or indeterminate authority dependency. A composed security conclusion must not become stronger than its verified dependencies.

This distinction follows the verifier-facing model in the individual Internet-Draft [Security Principal and Verifier Binding for Agent Communication Protocols](https://datatracker.ietf.org/doc/draft-bu-agentproto-security-principal-binding/) (`draft-bu-agentproto-security-principal-binding-06`, work in progress, intended Informational). It is architectural guidance, not an adopted IETF standard or validation of ODR.

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

## Human approval is an attack surface

A human approval gate is a privileged security boundary. The presence of an approval event does not prove that an authenticated, authorized human approved the exact action that executed.

```text
APPROVAL EVENT
      ≠
AUTHENTICATED HUMAN ACT
      ≠
AUTHORIZED HUMAN ACT
      ≠
EXACT-SCOPE APPROVAL
      ≠
EXECUTION WITHIN APPROVED SCOPE
```

**CVE-2026-58482** provides a concrete example. Network-AI versions 5.0.0 through 5.12.1 exposed mutating `ApprovalInbox` approval endpoints without authorization and returned wildcard CORS headers. A party able to reach the inbox could approve a pending high-risk operation without the intended human's consent. NVD maps the vulnerability to **CWE-862 (Missing Authorization)** and **CWE-352 (Cross-Site Request Forgery)**. Version 5.12.2 added optional bearer-secret protection for mutating approval endpoints.

The CVE demonstrates an authenticity and authorization failure at the approval interface. It does not demonstrate every approval-scope failure below.

| Boundary | ODR responsibility | Integrating-system responsibility |
|---|---|---|
| Principal authenticity | preserve the asserted approver and authority snapshot | authenticate the human and protect the approval channel |
| Approver authority | bind the asserted principal to a role assignment and recheck it at seal | provide a trusted, current authority source |
| Approval freshness | bind an expiry and consume the single-use authority on an execution attempt | protect session, nonce, and transport integrity |
| Exact action | bind approval to a canonical action hash | construct the correct action from trusted inputs |
| Execution reconciliation | refuse sealing when the recorded execution action hash differs | report or attest what actually executed |

ODR does not claim to prevent CVE-2026-58482. It addresses the downstream evidence boundary while relying on the integrating system for authenticated identity, protected transport, and trustworthy runtime observation.

Primary references:

- [NVD: CVE-2026-58482](https://nvd.nist.gov/vuln/detail/CVE-2026-58482)
- [GitHub Security Advisory: GHSA-mxjx-28vx-xjjj](https://github.com/Jovancoding/Network-AI/security/advisories/GHSA-mxjx-28vx-xjjj)
- [Fix commit](https://github.com/Jovancoding/Network-AI/commit/a59c13a1f0ce0e8a0779a90343eef92fac5ab4c3)
- [Network-AI v5.12.2](https://github.com/Jovancoding/Network-AI/releases/tag/v5.12.2)

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
14. Who verified each consequential claim?
15. Against what state, binding, freshness condition, and dependencies?
16. What exactly may the verifier conclude, and what does that result explicitly not prove?
17. What relying-party policy turns the bounded result into a decision?
18. What receipt preserves the evidence for these answers?

If a workflow cannot answer these questions, the action may be logged without its authority boundary being reconstructable.
