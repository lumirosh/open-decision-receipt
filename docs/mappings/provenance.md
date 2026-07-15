# Provenance and Conceptual Lineage

Open Decision Receipt sits within a known family of provenance, authorization, observability, and accountability structures. These comparisons are conceptual. They are not interoperability or conformance claims.

## Proof-Carrying Code

In Proof-Carrying Code, a program carries evidence that it satisfies a stated safety policy, and a verifier checks that evidence independently. A Decision Receipt applies a related pattern to a consequential decision: the receipt carries inspectable evidence, authority, scope, and execution references rather than requiring trust in the original decision-maker's narrative.

The current reference does not provide formal proofs.

## Time-of-check to time-of-use

CWE-367 describes the gap between checking a condition and later using it after the world may have changed. AI-assisted workflows have an analogous problem: a human or policy reviews evidence at check time, while execution occurs later against potentially different context. The receipt records both contexts so the gap can be detected.

## Software supply-chain provenance

SBOM, SLSA, and in-toto practices make software inputs, build steps, and attestations inspectable. A Decision Receipt applies a related provenance discipline to consequential actions by recording evidence, authority, policy, scope, execution, and accountability.

A Decision Receipt is not an SBOM or a SLSA/in-toto attestation unless a separate profile and interoperability contract explicitly establish that relationship.

## Observability

Traces can record model calls, tool calls, latency, errors, and execution paths. A Decision Receipt records a different concern: why a consequential action was authorized and whether the authorization basis still held when the action executed.

A trace can be referenced as receipt evidence. The receipt does not replace the trace.

## Authorization systems

Identity providers, policy decision points, access tokens, and enforcement systems determine whether an actor can reach a resource. A Decision Receipt can reference those controls and preserve the business or governance authority surrounding an action.

A receipt is not an OAuth token, bearer credential, or policy-enforcement decision. It must not be accepted as access authority unless a separate signed protocol explicitly defines and enforces that behavior.

## Signed action receipts

Emerging agent-security work uses signed receipts or attestations to prove that an identified actor invoked an action under a policy result. Open Decision Receipt focuses on the wider decision boundary: evidence, authority, approved scope, execution, accountability, and later drift.

Interoperability with signed action receipts is a research direction, not a current implementation claim.
