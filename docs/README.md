# Documentation

Start with one payment. Then follow the authority, evidence, and execution behind it.

## Start with the runnable story

- [AI agent payment run](./case-study-ap-payment-run.md): three roles share one credential; a fraud alert changes the basis for an approved run; a gate holds the next invoice. Includes the eight-scenario matrix, reconciliation, and explicit synthetic boundaries.
- [CLI quickstart](./quickstart.md): verify, approve, seal, replay, and reopen one decision step by step.

## Build or integrate

- [Architecture](./architecture.md)
- [Lifecycle](./lifecycle.md)
- [Google ADK workflows](../integrations/google_adk/README.md), an optional adapter with local mock actions
- [MCP verified-action bridge](./mcp-verified-action-bridge.md)

## Review the control model

- [Current limitations](./limitations.md)
- [Conformance levels](./mappings/conformance.md)
- [Security weakness mappings](./mappings/security.md)
- [Governance mappings](./mappings/governance.md)
- [Provenance and conceptual lineage](./mappings/provenance.md)
- [Combined reference index](./reference-mappings.md)

## Inspect other worked patterns

These examples demonstrate authority and evidence boundaries, not production readiness in each industry.

- [Loan denial](./case-study-loan-denial.md): independent evidence review, human authority, and bounded recorded execution
- [Analyst-gated SOC containment](../integrations/google_adk/README.md#soc-analyst-gated-containment): urgent, reversible action held for human review
- [Policy-authorized SOC containment](./case-study-soc-containment.md): narrow autonomy, accountable ownership, and reopening on drift
- [Claim payout](../examples/claim-payout-receipt.yaml): check-time and use-time context mismatch
- [Hallucinated legal precedent](./case-study-ai-hallucinated-precedent.md): unsupported evidence blocks authority
- [Certification-gated deployment](./quickstart.md#break-the-basis-and-watch-it-reopen): a changed basis reopens a previously sealed decision
- [RC3 end-to-end artifact bundle](../examples/end-to-end-artifact-bundle/README.md): resolved authority path, sealed parent, reopen event, and linked child revalidation

## Research direction

- [Signal map](../SIGNAL-MAP.md)
- [Structured-query evidence and future directions](./future-directions.md)
- [Decision Receipt Manifesto](../DECISION-RECEIPT-MANIFESTO.md)

The implemented contract lives in the schema, validator, lifecycle code, and tests. Research documents describe proposed directions and are not conformance requirements.
