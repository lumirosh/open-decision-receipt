# An appraisal for which action?

A synthetic integration example using the existing ODR lifecycle. No core API, schema or timestamp policy is changed.

From an ODR checkout with its declared dependencies installed:

```bash
python examples/appraisal-binding/probe.py
python -m pytest tests/test_appraisal_binding_example.py -q
```

Eight cases distinguish recorded action binding from appraisal/action correspondence:

1. An exact approved action without a source condition can seal.
2. A matching `ALLOW` condition can seal.
3. **Deliberate exposure:** the same generic `ALLOW` also permits the recorded lifecycle for a different action.
4. A missing required appraisal holds the check.
5. An appraisal changed before mock seal requires human review.
6. **Deliberate exposure:** a stored expected digest for A still permits B when nobody compares that digest with B's canonical action.
7. An **external wrapper gate** explicitly compares appraisal/action correspondence and holds B.
8. A matching appraisal/action passes that wrapper and can seal after separate synthetic approval.

The important distinction is assertion → appraisal → execution grant, not three interchangeable forms of authority: a source claims something; an appraisal evaluates a claim in context; an authorized approver permits a bounded action. This probe exercises only the narrow correspondence/lifecycle part. It does not qualify issuers or implement the upstream appraisal producer.

## Honest boundary

Every case has its own temporary synthetic policy/observation store. Actors, reviewer, source values and clock are trusted, unauthenticated fixtures. Cases3 and6 intentionally omit correspondence; they are not presented as vulnerabilities outside ODR's stated integration contract.

`GATE_HELD` is an early return in the wrapper, not evidence that a production resource stopped a payment. `sealed` records a caller-supplied mock execution object, not an independently observed effect. No real payment, signature, authenticated source, audience/policy-generation binding, concurrency, persistence or atomic resource admission is tested. A correct-looking appraisal can still contain false evidence.

Observation fixtures use `isoformat(timespec='seconds')` to align with the default condition-evaluation clock. The original uploaded microsecond-timestamp version fails at case2 on the pinned baseline because a same-second observation can appear later than the truncated evaluation time. That original failure is retained in the local research evidence; this adjusted example is not claimed to be the unchanged original.

Changing core clock precision is a separate proposal, not implemented here. Any such change must preserve rejection of genuinely future observations and test sub-second freshness boundaries. Integrations can already supply an explicit, consistently sampled `evaluated_at`; this example does not change that API or grant a future-time tolerance.

See [limitations](../../docs/limitations.md) and the [resource-side continuity reference](../../integrations/authority_continuity/README.md). That reference consumes a grant with its own synthetic effect; this probe does not provide or replace that admission guarantee.
