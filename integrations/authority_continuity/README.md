# Authority-continuity reference

This optional adapter imports an actual authorized receipt from ODR's `BundleStore`, `verify_action`, and `approve` APIs. A local SQLite transaction then checks the registered action hash, approval expiry, basis generation and snapshot, and owner epoch before consuming the grant and recording one synthetic effect. This is resource-side behavior in the example, not core ODR enforcement or an added default policy such as separation of duties.

Run from the repository root with Python 3.11 or later:

```bash
python -m integrations.authority_continuity.reference
python -m pytest -q tests/test_authority_continuity.py
```

The demo uses an isolated temporary directory by default and prints JSON. `--out DIR` keeps its SQLite database and policy fixture in the specified directory. The test command requires the project's development dependencies to be installed.

A basis snapshot or enabled-state change requires a strictly greater generation; generation cannot decrease. Republish does not revive an old grant. The resource checks approval expiry against its own system clock, not a caller-supplied time. A successful pay consumes the grant and records its effect atomically in this local SQLite database. The demo then hands ownership to a recovery observer, increments the fencing epoch, and sets a recovery hold. Handover grants no permission to send or resend. Reconciliation looks up a matching effect in this same local mock ledger: a match is `RECONCILED`; no match remains `UNKNOWN`. Reconciliation does not independently observe a payment-provider outcome.

The journal is a mutable current-state table, not an immutable audit ledger. The policy, actor, approver, basis, and handover registry are trusted but unauthenticated fixture inputs. This example provides no real PSP or money movement, IAM, cryptographic authority, independent outcome attestation, schema migrations, or cross-store transaction. It has no automatic resend, clear-hold, or resume API. SQLite behavior here is not PostgreSQL race proof and does not reproduce separate PostgreSQL/Docker crash or race experiments. Nothing in the adapter changes the ODR receipt contract or enforces actions outside this example.
