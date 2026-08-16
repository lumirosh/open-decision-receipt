# Limitations

Open Decision Receipt is deliberately small. Its credibility depends on not overclaiming.

## A receipt is not runtime enforcement

A Decision Receipt records why an action was allowed, denied, escalated, sealed, or reopened. Runtime controls still decide what actually executes.

Production systems may consume receipt verdicts, but the receipt itself is not a firewall, IAM layer, workflow engine, or policy enforcement point.

## A receipt is not identity binding

The reference implementation treats actors as strings. It does not prove that `release_workflow`, `operator`, or any named role corresponds to a cryptographic identity or authenticated session.

Identity binding belongs in the integrating system.

## A resolved path is not an authority service

The reference resolver projects one exact path from a supplied authority bundle. It does not discover organizational authority, authenticate its source, replace IAM or policy enforcement, or make observed behavior authoritative. Integrating systems remain responsible for trusted bundle provenance and runtime enforcement.

## Recorded execution binding is exact, not semantic or independent

The reference lifecycle binds request, approval, and recorded execution to a canonical action and refuses sealing when their action hashes differ. This is exact object equality, not semantic subset reasoning: it does not decide whether one transfer limit, query, trajectory, or sequence is safely contained within another.

The executor still supplies the execution record. ODR does not independently observe a tool, external system, or real-world outcome, and it does not yet record a named comparison method/version or a separate `match | mismatch | insufficient_evidence` verdict. Integrations that require independent outcome assurance must provide trusted execution attestation or observation.

## The hash chain is not a signature scheme

`dam_verify.chain` is tamper-evident, not tamper-proof. It can show that local receipt history was modified after the fact. It does not replace digital signatures, trusted timestamping, HSM-backed signing, or external notarization.

## Evidence can still be wrong

A receipt records what evidence was visible and what basis was checked. It does not prove that the original evidence was true, complete, or honestly produced.

Bad evidence with a good receipt is still bad evidence. The receipt makes that dependency visible. Structured-query evidence can record a query's provenance and a result commitment, but it does not prove the query backend, source material, or result was true. See [`future-directions.md`](./future-directions.md).

## Human approval is not automatically good approval

The receipt binds explicit approval to an asserted approver, assigned role, authority snapshot, expiry, and canonical action. The reference implementation does not prove cryptographic identity, organizational authority beyond the supplied bundle, competence, independence, freedom from pressure, or authorship.

That is why the schema records dissenting signals, separation of duties, approval basis, and accountability.

## Failed-seal consumption depends on persistence

`seal()` consumes authority in the returned receipt as soon as execution is attempted, and the shipped CLI and adapters persist that result. The library call and persistence step are not one atomic store transaction. A custom host that discards a failed `seal()` result and reloads the earlier authorized receipt can lose the consumption record. Library integrations must persist every seal result; a future store-level transaction is required before claiming atomic one-shot enforcement across arbitrary hosts.

## Not legal advice

Regulatory mappings are implementation aids, not legal advice. Use counsel and domain experts for binding interpretations.

## Current reference implementation boundaries

The reference code is intentionally boring:

- flat-file bundles and receipts
- local hash chain
- simple JSON/YAML examples
- no network service
- no user management
- no database migration layer
- no production runtime policy engine

Those omissions are intentional. The repo defines the portable receipt object and a minimal lifecycle, not a full governance platform.
