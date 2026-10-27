# Open Decision Receipt

## Approved at 09:00. Still authorized at 09:20?

A controller approves twelve supplier payments. Fifteen minutes later, a fraud alert opens on one supplier. The agent reaches the next payment five minutes after that.

The approval did not change. Its basis did.

**Open Decision Receipt (ODR)** is a vendor-neutral receipt format and Python reference lifecycle that binds an exact action to its recorded authority, evidence, and execution.

A trace shows what ran. A Decision Receipt makes the basis for allowing it inspectable.

## Run the payment demo

Requires Python 3.11+. From a Python environment where you can install packages:

```bash
git clone https://github.com/lumirosh/open-decision-receipt.git
cd open-decision-receipt
python -m pip install -e '.[dev]'
python scripts/ap-payment-run-demo.py
```

The [synthetic payment run](./docs/case-study-ap-payment-run.md) shows three things:

1. **Three roles, one credential.** The decision rule denies a bank-detail change; the shared credential could still make it.
2. **A valid approval, a changed condition.** At 09:20 the demo's runtime gate holds invoice 7. If bypassed, ODR refuses to seal the recorded action.
3. **A stop is not a rollback.** Six payments are already committed in the simulation. One went to the alerted supplier before the alert and needs a recall or confirmation decision.

```text
Committed and sealed                      6      $42,000
Held at the gate                          1      $18,500
Queued, not attempted                     5      $34,400
Already paid to VENDOR-X before alert     1       $9,800
```

The $9,800 is part of the committed $42,000, not an additional payment.

**This is a simulation, not a banking integration.** Data, identities, permissions, clock, and gate are synthetic. ODR does not move money or stop actions by itself.

Run the eight-scenario matrix, export its evidence, or run the tests:

```bash
python scripts/ap-payment-run-demo.py --suite
python scripts/ap-payment-run-demo.py --suite --out ./ap-demo-evidence
python -m pytest -q
```

The matrix covers valid payments, changed bank details, fraud alerts, out-of-role actions, revoked approvers, unavailable feeds, stale checks, and excess credential privileges. Its 300-second credential cache is an assumption, not measured IAM latency.

## What the receipt preserves

- **Authority:** the asserted approver or policy rule, scope, role, and validity window.
- **Action:** the exact canonical action approved and the execution record supplied by the executor.
- **Basis:** the evidence and conditions checked, including whether they still held at use.
- **History:** a sealed record; later drift can append a reopen event and linked child without rewriting the parent.

Missing authority or required evidence does not become approval. A changed action, expired approval, or broken bound condition refuses sealing. Refusing a seal after execution is evidence, not prevention: the integrating runtime must check before acting.

See the complete [lifecycle](./docs/lifecycle.md), [receipt example](./examples/loan-denial-receipt.yaml), and [replayable artifact bundle](./examples/end-to-end-artifact-bundle/README.md).

## Use it in your workflow

1. Supply trusted policy, evidence, and authenticated actor information.
2. Verify the proposed action and obtain scoped approval where required.
3. Recheck at the runtime boundary, execute only if permitted, and persist the execution and seal result, including failures.
4. Watch the referenced basis and require a new lifecycle when it changes.

ODR supplies the record and reference checks. Your integration owns authentication, permission enforcement, action execution, and independent outcome observation. The reference library does not provide atomic, cross-process one-shot enforcement; see [persistence limitations](./docs/limitations.md#failed-seal-consumption-depends-on-persistence).

## Go deeper

- **Build:** [CLI quickstart](./docs/quickstart.md), [optional Google ADK workflows](./integrations/google_adk/README.md), [MCP bridge](./docs/mcp-verified-action-bridge.md).
- **Review:** [architecture](./docs/architecture.md), [conformance levels](./docs/mappings/conformance.md), [limitations](./docs/limitations.md).
- **Explore:** [all documentation, worked cases, mappings, and research](./docs/README.md).

Schema validation is not a governed workflow: L1 checks documentation, L2 records binding, and L3 requires lifecycle behavior. The mappings are implementation aids, not compliance certification.

## Boundaries

ODR is an open receipt format and minimal reference implementation, not an IAM system, runtime enforcement engine, GRC suite, signature scheme, or legal opinion.

Actors and authority sources are supplied by the integration. A matching action hash binds recorded objects; it does not independently prove identity, legitimate authority, true evidence, or a real-world outcome. Read the [full limitations](./docs/limitations.md) before relying on a receipt.

## Contributing and license

Improve the evidence boundary without bypassing it. See [CONTRIBUTING.md](./CONTRIBUTING.md) and [SECURITY.md](./SECURITY.md).

Apache-2.0. Maintained by [LumiRosh Research](https://lumirosh.com).
