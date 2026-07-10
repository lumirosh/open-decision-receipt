# Decision Receipt Lifecycle

The canonical lifecycle guide is [`docs/lifecycle.md`](./docs/lifecycle.md).

A Decision Receipt moves through four phases:

```text
verify authority and evidence
→ authorize a bounded action
→ seal only when check-time equals use-time
→ reopen when evidence or authority basis drifts
```

For the runnable reference implementation, start with the [Quickstart](./docs/quickstart.md).
