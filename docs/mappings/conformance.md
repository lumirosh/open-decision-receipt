# Conformance Levels

A Decision Receipt can be validated at three additive levels. L2 includes L1. L3 includes L1 and L2.

| Level | Name | What it demonstrates | Reference validation |
|---|---|---|---|
| **L1** | Documented | Required fields are present and schema-valid | `dam-verify validate <receipt>` passes without schema errors |
| **L2** | Bound | Check-time and use-time contexts are recorded and linked | L1 plus `dam-verify chain` reports an intact chain |
| **L3** | Governed | Authority is resolved before execution, check and use are compared at seal, and watch can reopen the receipt when its evidence or authority basis changes | L2 plus a lifecycle-managed sealed receipt that reopens after a relevant basis change |

The reference implementation can produce receipts at any level. Most workflows should reach L2. High-consequence workflows should target L3.

Conformance describes observable receipt and lifecycle behavior. It does not certify evidence truth, identity authenticity, legal compliance, production security, or organizational governance quality. See [limitations](../limitations.md).
