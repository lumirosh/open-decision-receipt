# JEP / HJS / Decision Receipt boundary case

Status: illustrative worked case, not a conformance or interoperability claim.

Specification basis:

- JEP Core 0.6 (`draft-wang-jep-judgment-event-protocol-06`)
- HJS Core 1 (`draft-wang-hjs-accountability-05`)
- Open Decision Receipt v0.2 RC schema

HJS-05 normatively references JEP-05. Using JEP-06 with HJS-05 here follows the current working comparison, not a conformance claim.

## Case

A delegated agent may update a customer's mailing address (Action A). Action A has already committed when the agent discovers adjacent work: updating the same customer's credit limit (Action B). The delegation does not name that field. The runtime must not silently expand authority.

## Object order

1. `delegation-event.json` records the JEP delegation claim for Action A.
2. `scope-comparison.json` compares candidate Action B with the delegated scope and returns `not_contained`.
3. `verification-event.json` records the comparator result as a JEP verification claim.
4. `decision-receipt.json` binds the authority, candidate action, comparator result, partial-effect state, and fail-closed lifecycle decision.
5. `hjs-manifest.json` packages the event and evidence digests last.

The graph is intentionally acyclic:

```text
delegation -> comparison -> verification -> Decision Receipt -> HJS manifest
```

The HJS manifest is not referenced from inside the package. The Decision Receipt is carried as external evidence rather than re-described as an HJS behavior record. This is the smallest arrangement that tests a distinct portable role without inventing duplicate receipt semantics. It is therefore a structural manifest draft, not a valid HJS receipt: HJS receipt validation requires a JEP event bound to the HJS object. Whether that binding can be added without circular receipt semantics is deliberately left for the comparison.

## Layer ownership in this example

| Layer | Claim |
|---|---|
| Comparator | Candidate Action B is not contained in the supplied scope under the named policy and version. |
| JEP | Actors issued delegation and verification claims with typed semantics and digest references. |
| Decision Receipt | Action B lacked matching authority, was not attempted, and requires a new authority decision; Action A remains committed. |
| HJS | The listed events and evidence objects form one digest-addressed package. |
| Runtime | Must enforce the pause; enforcement is not proved by these files. |

## Explicit non-claims

This fixture does not prove:

- that the illustrative JEP signatures are cryptographically valid;
- that actor identifiers resolve to real identities;
- that the delegator held legally effective authority;
- that the comparator policy is adequate outside this exact object shape;
- that Action A occurred externally as recorded;
- that a runtime enforced the pause;
- that JEP, HJS, and ODR are interoperable specifications.

The `sig` values are deliberately labelled illustrative. They are not conformance vectors.

## Verification

```bash
python3 -m pytest tests/test_jep_hjs_boundary_case.py -q
```

The test validates the ODR object against the repository schema, recomputes digest references using canonical key ordering for this ASCII/integer-only fixture, asserts the intended acyclic reference topology, and preserves the partial-effect boundary: Action A committed; Action B not executed. The digest helper is not a general JCS implementation.
