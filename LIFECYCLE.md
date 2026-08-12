# Decision Receipt Lifecycle

The canonical lifecycle guide is [`docs/lifecycle.md`](./docs/lifecycle.md).

A Decision Receipt follows one authority-to-accountability lifecycle:

```text
Observed → Proposed → Mandated → Authorized → Prepared
→ PreCommitVerified → Committed → ResultObserved
→ Reconciled → Sealed
```

Post-seal monitoring may append a `ReopenEvent` and start a linked child
lifecycle. It never mutates the sealed parent receipt.

For the runnable reference implementation, start with the [Quickstart](./docs/quickstart.md).
