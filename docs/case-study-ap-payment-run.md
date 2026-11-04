# Case study: an AI agent payment run

Status: synthetic, executable worked case. Not a production integration, not a conformance claim.

An accounts-payable run is approved at 09:00. Six invoices are paid. At 09:15 something in the world changes. At 09:20 the payment agent reaches the next invoice. Was the 09:00 approval still enough?

This is a time-of-check to time-of-use (TOCTOU) problem expressed through business authority, not through files or memory. The approval was valid when it was given. The question is whether its basis still held when the action ran.

```bash
python3 scripts/ap-payment-run-demo.py            # vertical slice: three scenes
python3 scripts/ap-payment-run-demo.py --suite    # eleven tests, thirteen scenarios
python3 scripts/ap-payment-run-demo.py --suite --out evidence/   # also write JSON evidence
```

## The workflow

| Worker | Declared to do | Not appointed to do |
|---|---|---|
| `invoice_agent` | match invoices to purchase orders | pay, change bank details |
| `vendor_master_agent` | propose a bank-detail change | apply the change, pay |
| `payment_agent` | pay approved invoices to verified beneficiaries | change bank details, approve payments |
| `controller.priya` (human, `ap_controller`) | approve the run | |

Recommend, approve and execute sit with different actors. The 09:00 approval is valid for four hours. The run policy treats any open fraud alert on a payee, or an unverified or stale beneficiary check, as a reason to pause the whole run until a human revalidates.

## Three states that change independently

| State | What can change | Who owns it |
|---|---|---|
| Worker | identity, credential, role assignment, model or tool version | IAM and the runtime control plane |
| Decision | the exact action proposed, approved, prepared and attempted | the Decision Receipt (action hash binding) |
| Environment | fraud alerts, beneficiary verification, policy | the receipt's bound conditions (HOLDING, STALE, BREACHED, UNKNOWN) |

Execution is justified only when all relevant conditions still hold at the consequence boundary.

## The gate and the clock

For the scenarios modelled here, the synthetic gate checks the approval window, the approver's role, the exact payment instruction, and the bound conditions before each payment. These are not a complete production enforcement contract. A refused seal after the money has moved is evidence, not prevention, so the corresponding pre-commit checks belong at the runtime gate.

The demo runs on one simulated clock. The reference engine normally reads the wall clock; the demo drives that clock so approval, expiry, execution and seal timestamps in the receipts match the scenario timeline.

## The vertical slice

1. **Declared roles vs effective credential.** Three roles, one shared service account. When the payment agent asks to update a vendor's bank details, the receipt engine returns DENIED. The credential could still do it. The decision record says no; the credential says yes.
2. **The run.** Twelve invoices approved at 09:00. INV-001 to INV-006 pass the gate and seal. A fraud alert on VENDOR-X arrives at 09:15. INV-007 reaches the gate at 09:20 and is held; its approval is never consumed. Had an executor bypassed the gate, ODR would have refused to seal.
3. **Reconciliation.** USD 42,000 committed, 18,500 held, 34,400 queued. USD 9,800 had already gone to VENDOR-X at 09:06, before the alert. Sealed receipts do not undo payments; that invoice needs a recall or confirmation decision.

## The acceptance suite (11 tests, 13 scenarios)

| # | Change | Gate at INV-007 | ODR if the gate is bypassed | Enforcement owner |
|---|---|---|---|---|
| 1 | none | all twelve pass and seal | sealed | runtime gate |
| 2 | VENDOR-X bank details changed at 09:16 | HOLD: instruction differs from approved action | refused: action commitment changed | runtime gate |
| 3 | fraud alert at 09:15 | HOLD: `fraud-alert-clear` breached | refused: condition breached | runtime gate |
| 4 | `vendor_master_agent` asks to pay | n/a | DENIED: action outside its allowed set | runtime gate and chain policy |
| 5 | controller's role removed at 09:18 | HOLD: approver authority changed | refused: approver authority changed | IAM and runtime gate |
| 6 | fraud feed unreachable at 09:16 | HOLD: `fraud-alert-clear` unknown | refused: condition unknown | runtime gate (fail closed) |
| 7 | beneficiary check older than 24h | HOLD: `beneficiaries-verified` stale | refused: condition stale | runtime gate |
| 8 | three roles share one credential | n/a | DENIED for the out-of-role action | IAM (effective privilege finding) |
| 9a | true alert at 09:15, cached `none` from 08:58, 3600s freshness window | PASS: EXPOSED, USD 18,500 paid to VENDOR-X | sealed: the recorded observation still passes | runtime gate and source integration |
| 9b | same frozen source, pull at approval/execution, 60s freshness window | HOLD: `fraud-alert-clear` stale | refused: condition stale | runtime gate and source integration |
| 10a | bank witness freshly lies `none`; PSP and SIEM report VENDOR-X | HOLD: PSP and SIEM breached, not bank | refused: conditions breached | runtime gate and independent witnesses |
| 10b | no real alert; PSP plants an alert on VENDOR-B | HOLD: PSP breached; no payments after 09:15 | refused: condition breached | runtime gate; attacker causes delay, not payment |
| 11 | fooled gate from 9a plus USD 50,000 / rolling 30-minute cap | HOLD: `blast-radius cap` | **sealed**: the cap is a gate-only rule, not checked by ODR | runtime gate and shared budget in a real integration |

Test 5 also reports revocation latency in two layers. At the decision layer, no action was accepted after the revocation and the first attempt (09:20) was refused. At the credential layer, an assumed 300-second token cache would keep the shared credential usable until 09:23. The second number is an assumption, not a measurement of any real IAM system; in a real review it is measured.

Tests 4 and 8 rely on exact rule checks. ODR does not decide whether one action is semantically contained in another, and it does not discover credentials.

## Feed trust

<!-- credit: pending -->

- *Silence isn't evidence: the gate asks at execution.*
- *One witness can stop a payment; it takes all of them to release it.*
- *Three feeds from one upstream are one witness wearing three badges.* Independence is **assumed** here; in a real Review it is a finding, not a given.

The source model is opt-in. Default runs and tests 1–8 still consume the original observation snapshots. Pull mode asks every bound source at approval and before each attempted payment. `live` returns current synthetic truth with the query timestamp; `frozen` returns its last answer unchanged; `down` supplies no observation; `silenced` lies with a fresh `none`; `false_alarm` names the attacker's chosen vendor with a fresh timestamp. A fresh answer is not proof of truth.

In 9a the lazy gate retains `none` from 08:58. At 09:20 its 22-minute age is inside the bound 3600-second window, so the dangerous PASS is the expected **EXPOSED** result, not a failing suite. In 9b, earlier pulls advanced the last answer to 09:12 before the source froze at 09:15; at 09:20 that answer is eight minutes old and exceeds the bound 60 seconds. We do not backdate it to 08:58. Approval succeeds because the gate also pulls at 09:00.

The three-witness bundle has **no `compensation` block**, either at bundle level or in its authority rules. Do not add a majority `k_of_n`: it would let healthy-looking witnesses outvote a breached or stale witness, changing the release rule. Missing or stale witnesses also hold the run. A planted alert pauses the whole run; it does not select, reroute or authorise a payment to the named vendor. This trades availability for the specified stop rule; it is not denial-of-service resistance.

Sources, modes and independence are synthetic assumptions, not production connectors, authenticated attestations or proof of compromise resistance. Condition definitions and source references are chosen **before** approval and stay bound by the existing authority hash. No engine or schema change is required.

## Blast-radius cap

Test 11 reuses the fooled gate in 9a, not the asking gate. The optional `run_cap = {"usd": 50000, "window_minutes": 30}` holds an instruction when sealed payments across **all payees** in `(execution time - 30 minutes, execution time]`, plus the proposed amount, would exceed USD 50,000. Equality is allowed; payments leave the rolling window at its left boundary. A default `None` leaves tests 1–10 unaffected.

The first six payments total USD 42,000. INV-007 would bring the window total to USD 60,500, so the cap holds it even though the stale-but-accepted fraud observation still says `none`. Total paid to VENDOR-X over the run falls from **USD 32,700 without the cap to USD 9,800 with it**. Both figures include the USD 9,800 paid before the alert; neither implies recovery. The tests assert the rolling-window property, including exact-limit and window-expiry cases, rather than only these sample totals.

**If the cap gate is bypassed, ODR still seals.** The cap is a separate synthetic gate rule; it is not in the ODR engine, schema or hashed condition definitions. It bounds only this single-process run's modeled payments. Other runs, concurrent workers, alternate payment routes, durable budget accounting and atomic reservations are not implemented. Sources, modes and the cap are synthetic, not a production payment control.

## In change-control terms

Every consequential agent action deserves change-control discipline, without turning each one into a ticket.

| ODR stage | Change-control analogue | In this run |
|---|---|---|
| Mandated | standing authority with limits | the run policy and role contract |
| Authorized | change authority approves | the controller's 09:00 approval |
| PreCommitVerified | pre-implementation check | the gate before each payment |
| Committed | implementation | a payment sent |
| Sealed | closure | committed payments retain their sealed receipts |
| Held, pending revalidation | pre-implementation hold | unexecuted invoices need current checks before resuming |

This slice holds unsealed invoices; it does not demonstrate a post-seal `ReopenEvent`. See the [end-to-end artifact bundle](../examples/end-to-end-artifact-bundle/README.md) for a sealed parent and linked child revalidation.

Pre-authorise the routine. Recheck what changes. Stop what falls outside the mandate. Verify what actually happened.

## Boundaries

Everything here is synthetic: invoices, vendors, the IAM inventory, the token cache, the clock and the execution gate. ODR recorded who approved what, under which conditions, and refused to seal when the basis broke. It did not verify identities, discover credentials, move money, or stop anything on its own.

A receipt can explain why an action was justified. The enforcement point must prove whether an unauthorised action was actually stopped.
