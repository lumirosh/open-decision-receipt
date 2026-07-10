# Limitations

Open Decision Receipt is deliberately small. Its credibility depends on not overclaiming.

## A receipt is not runtime enforcement

A Decision Receipt records why an action was allowed, denied, escalated, sealed, or reopened. Runtime controls still decide what actually executes.

Production systems may consume receipt verdicts, but the receipt itself is not a firewall, IAM layer, workflow engine, or policy enforcement point.

## A receipt is not identity binding

The reference implementation treats actors as strings. It does not prove that `release_workflow`, `operator`, or any named role corresponds to a cryptographic identity or authenticated session.

Identity binding belongs in the integrating system.

## The hash chain is not a signature scheme

`dam_verify.chain` is tamper-evident, not tamper-proof. It can show that local receipt history was modified after the fact. It does not replace digital signatures, trusted timestamping, HSM-backed signing, or external notarization.

## Evidence can still be wrong

A receipt records what evidence was visible and what basis was checked. It does not prove that the original evidence was true, complete, or honestly produced.

Bad evidence with a good receipt is still bad evidence. The receipt makes that dependency visible. Structured-query evidence can record a query's provenance and a result commitment, but it does not prove the query backend, source material, or result was true. See [`future-directions.md`](./future-directions.md).

## Human approval is not automatically good approval

The receipt proves scoped human authorship. It does not prove the human was competent, independent, unbiased, or free from pressure.

That is why the schema records dissenting signals, separation of duties, approval basis, and accountability.

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
