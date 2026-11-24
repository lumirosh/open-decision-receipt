# Local freshness and alternative-path vectors

A small synthetic fixture inspired by the [A2A #1937 discussion](https://github.com/a2aproject/A2A/issues/1937#issuecomment-7131501126). It reuses ODR's `evaluate_conditions` and `canonical_action`; it is **not an A2A adapter, accepted conformance suite, or live authority service**. No core ODR behavior changes.

## Run

From the repository root, with the project's normal and development dependencies installed:

```bash
python3 examples/a2a_freshness_vectors.py
python3 examples/a2a_freshness_vectors.py --json
python3 -m pytest -q tests/test_a2a_freshness_vectors.py
```

The demo prints observations, not a self-certified PASS. The separate acceptance oracle specifies the expected outcomes and checks real local callback counts. There are **14 scenarios inside one pytest acceptance test**, not 14 independent test functions.

## The contract being exercised

- Source-established `as_of` maps to ODR's `last_validated_at`. Retrieval is separately recorded and cannot reset observation age.
- The declared maximum age is 60 seconds, inclusive at exactly 60 seconds under the existing evaluator.
- The source's ACTIVE observation at 10:00 passes at 10:00:30. Re-fetching that same observation at 10:01:30 leaves it stale.
- A genuinely new authoritative observation at 10:01:20 can support the 10:01:30 decision even if its ACTIVE value is unchanged. A new timestamp/reference is **asserted trusted input** here, not proof that the source actually made the observation.
- Missing age, a future observation and fresh REVOKED evidence remain distinct unknown/breached findings and do not dispatch.
- Each candidate path is evaluated independently. A fresh alternative must bind the same caller, delegate, task, context and exact effect. A fresh unrelated caller, delegate, task, context or target does not rescue a stale path.
- If two paths are eligible, this single invocation chooses one and invokes the local callback once. This does not establish durable idempotency or concurrent one-shot consumption.

The JSON includes the decision time, asserted evidence/source references, original as-of and retrieval times, per-path binding comparisons, existing condition-evaluation details, selected path, and local dispatch log. `dispatch_log` is a list in the fixture process, not independent real-world outcome evidence.

## Oracle sensitivity

The acceptance check was also exercised against two deliberately weakened disposable copies: replacing source age with retrieval age, and ignoring exact binding. Each weakening made the acceptance test fail. The unchanged implementation and the existing repository suite passed. These are local negative controls, not measurements of any A2A product.

## Limits

The caller/delegate identities, grants, trusted sources, observation times and independent authority of the alternative are declared fixtures. There is no source authentication, signature verification, A2A transport, chain reconstruction, real dispatch, instantaneous-revocation guarantee, distributed reservation or external-provider recovery. A source that lies with a fresh timestamp is outside this fixture's guarantees. ODR does not become the runtime enforcement point because this example invokes a list callback.
