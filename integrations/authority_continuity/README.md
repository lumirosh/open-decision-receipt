# Authority-continuity reference

This is an **optional synthetic SQLite reference**, not part of ODR core or its schema. It generates an authorization through ODR's real `BundleStore`, `verify_action`, and `approve` APIs, then demonstrates a local synthetic effect and a recovery hold.

Run:

```bash
python -m integrations.authority_continuity.reference
python -m pytest -q tests/test_authority_continuity.py
```

The example adapts ideas from earlier resource final-admission and recovery-handover experiments. It is deliberately a smaller local subset, not a reproduction of their PostgreSQL or separate-process tests.

Changing a basis snapshot or eligibility requires a strictly newer generation; decreasing it is refused. Republish does not revive an old grant. The resource checks recorded approval expiry against its own clock, not a caller-supplied timestamp. Recovery handover may restrict future sends but cannot downgrade an already reconciled outcome.

The policy, actor, approver, basis, and handover registry are trusted but unauthenticated fixture inputs. This example does not provide a real PSP, money movement, IAM, cryptographic authority, independent outcome attestation, migrations, or a cross-store transaction. It has no automatic resend, clear-hold, or resume API. Recovery observation can reconcile only a matching effect in this same local mock ledger; no matching fact remains `UNKNOWN`. SQLite concurrency here is not PostgreSQL race proof. Nothing in this adapter changes what an ODR receipt means or enforces actions outside this example.
