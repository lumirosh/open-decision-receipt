# An appraisal for which action?

Two synthetic experiments share one fixture: an eight-case mock-seal probe and a twelve-case composition with the existing SQLite resource. No core API, schema or timestamp policy is changed. This is an integration contract and counterexample pack, not a new protocol or production security system.

From an ODR checkout with its declared dependencies installed:

```bash
python examples/appraisal-binding/probe.py
python examples/appraisal-binding/resource_probe.py
python -m pytest tests/test_appraisal_binding_example.py tests/test_authority_continuity.py -q
```

Both commands use temporary state. The first prints case results; the second prints JSON with native effect rows, grant state, receipts, refusals, call counts and controlled event order. Completion is reported only after cleanup. Nothing moves money or calls a provider.

## 1. Appraisal correspondence: eight cases

1. An exact approved action without a source condition can seal.
2. A matching `ALLOW` condition can seal.
3. **Deliberate exposure:** the same generic `ALLOW` also permits the recorded lifecycle for a different action.
4. A missing required appraisal holds the check.
5. An appraisal changed before mock seal requires human review.
6. **Deliberate exposure:** a stored expected digest for A still permits B when nobody compares that digest with B's canonical action.
7. An **external wrapper gate** explicitly compares appraisal/action correspondence and holds B.
8. A matching appraisal/action passes that wrapper and can seal after separate synthetic approval.

In this first probe, `GATE_HELD` is an early return, not evidence a resource stopped a payment. `sealed` records a caller-supplied mock execution, not an independently observed effect. Cases3/6 deliberately omit correspondence; they are not vulnerabilities outside ODR's stated integration contract. Issuer trust, audience/policy-generation appraisal binding, persistence, concurrency and resource admission are not tested by these eight cases.

## 2. Appraisal → grant → resource: twelve controlled schedules

The extension reuses `probe.prepare` for the same bundle/observation/check fixture, obtains a separate synthetic approval, and imports that actual receipt into [the existing continuity resource](../../integrations/authority_continuity/README.md). It does not reimplement admission logic.

The strict expected condition is derived from the **actual requested canonical action**; its observation is independently supplied as a fixture. Existing equality conditions can therefore express correspondence when the trusted integration supplies the correct expectation. The unbound case deliberately supplies the wrong one.

The resource checks its own action, basis, owner, expiry and consumption before consuming a grant with its local SQLite effect. The extension reads back the persisted effect commitment and registered payload before sealing, rather than treating the request's canonical object as outcome proof. That is a trusted local resource observation, not independent provider attestation.

| Controlled case | Terminal stage / receipt | Pay calls | Local effects |
|---|---|---:|---:|
| Matching appraisal and exact grant | `sealed` | 1 | 1 |
| Appraisal A, request B, correctly bound expectation | `CHECK_HELD` | 0 | 0 |
| **Exposed:** unbound appraisal A reused for approved B | `sealed` | 1 | 1 |
| Action changed after approval | `RESOURCE_REFUSED` | 1 | 0 |
| Source changes before wrapper check | `GATE_HELD` | 0 | 0 |
| **Exposed:** bypass after source-only change | `needs_human_review` | 1 | 1 |
| **Exposed:** source changes after passing wrapper check | `needs_human_review` | 1 | 1 |
| Resource-first withdrawal after wrapper check | `RESOURCE_REFUSED` | 1 | 0 |
| Resource withdraws/reactivates with newer generation | `RESOURCE_REFUSED` | 1 | 0 |
| Source/basis changes only after effect committed | `needs_human_review` | 1 | 1 |
| **Exposed:** matching trusted appraisal contradicts fixture truth | `sealed` | 1 | 1 |
| Same consumed grant called twice | First receipt remains `sealed`; second call refused | 2 | 1 |

Each row starts a distinct fresh operation. These are not one payment run or a security success rate. Calls include refused attempts; effects are native committed local rows. The JSON retains exact reasons/hashes. The existing resource uses `basis or action commitment changed` for both failures; this experiment does not invent finer native reason codes.

### Formation is not continuity

Exact binding preserves the action that was approved. If B was formed from an unrelated appraisal and approved anyway, the resource can faithfully execute B and the receipt can seal. Consistency does not retroactively justify formation. With an expectation derived from actual B, the A-for-B request instead holds before approval.

### A source update is not resource publication

The wrapper and resource read different state. A source-only change does not automatically revoke an imported resource grant. The passing-check-then-source-change case needs no deliberate bypass: it exposes the precheck/use window.

The withdrawal case writes the stricter resource state first, then the source. The native resource then refuses before its effect. This is a controlled trusted-publisher ordering, not atomic publication across two stores, automatic propagation, or measured revocation latency. A resource only enforces the basis it actually has.

### Restored values do not restore the old grant

Withdrawal advances generation2 and reactivation generation3 even though snapshot/enabled values return to the original state. The generation1 grant remains unusable. This tests the existing resource's local monotonic-generation check, not universal terminal revocation.

### Seal refusal has different histories

`needs_human_review` occurs when the source changed before the effect but a wrapper was bypassed, when it changed after a passing check but before effect, and when it changed only **after a valid local effect committed**. Final seal status alone cannot determine when drift happened or establish that the effect was unauthorized at its actual commit. Reconstruct event order and resource state; seal refusal is not rollback.

### Refusal does not mean no earlier effect

A repeated consumed grant produces a refused second call while the first effect and sealed receipt remain. A refusal under this local contract means that attempt created no new effect, not that no prior effect exists. The output preserves call count, refusal and the existing effect together.

### Matching is not truth

The false-appraisal control has matching commitment, approval, effect and sealed receipt, while a separate fixture-only oracle says A rather than B. The oracle is deliberately excluded from gate inputs. This is not real fraud detection; it makes the trusted-producer assumption visible.

## Working vocabulary

- **Assertion:** what a source claims about a subject/field; source qualification is separate from authentication.
- **Appraisal:** evaluation of evidence for an action/context, not automatically permission to execute.
- **Execution grant:** bounded permission, obtained here by a separate synthetic approval.
- **Admission:** the resource's current checks at its local effect transaction, not a prior receipt or wrapper success alone.
- **Execution observation:** what a readback establishes; here only a trusted local SQLite effect.
- **Receipt:** recorded authority, checks and execution, including failures; not independent truth.

These are implementer distinctions, not novelty or standards-conformance claims.

## Evidence boundaries and stopping point

Policy, observations, actor/reviewer, basis publisher, owner and clock are trusted unauthenticated fixtures. No issuer qualification, signatures, cryptographic identity, audience/policy-generation appraisal binding or real provider outcome is implemented.

The twelve schedules are synchronous and single-process. They do not prove concurrent interleavings, distributed one-shot behavior, cross-store atomicity, provider idempotency or independent outcomes. Existing resource unit tests remain separate evidence. No resend, recovery, authority service, clock tolerance or production gate was added.

Regression checks preserve the original eight cases, compare native effect commitments with receipt/request commitments, check exact refusals/event order, ensure connection closure and inject cleanup failure. Disposable weakening controls outside shipped runtime show that a fixed-A expectation and removal of the existing resource basis guard break the acceptance oracle.

This batch stops at those controlled contracts and counterexamples. A real integration needs its own issuer trust, authenticated policy/publication path, resource admission and observation contract before any stronger claim.

## Clock precision remains a separate decision

Observation fixtures use `isoformat(timespec='seconds')` to align with the default condition-evaluation clock. The unchanged original fractional-timestamp probe can fail at case2 because a same-second observation is later than a truncated evaluation instant. That original failure is retained separately; it is not relabelled as the adjusted example passing.

Core precision was not changed. A future proposal must preserve rejection of genuinely future observations and test sub-second freshness boundaries. The existing `evaluated_at` API already permits a consistently sampled trusted evaluation time; this example grants no future-time tolerance.

See [limitations](../../docs/limitations.md) and [the continuity reference boundaries](../../integrations/authority_continuity/README.md).
