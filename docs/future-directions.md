# Future directions

This page tracks credible extensions to the Decision Receipt model that are not yet runtime capabilities. It is separate from [limitations](./limitations.md), which states what the current reference implementation does not claim.

## Structured-query evidence

### The gap

`check.evidence_seen` can record a plain evidence label such as `credit_score_report_v2`. That establishes what the receipt author says was reviewed. It does not, by itself, preserve a queryable account of how an evidence conclusion was produced.

A context hash can show whether the recorded check-time context equals the execution-time context. It does not establish the provenance, query semantics, or result representation behind an individual evidence item.

### The extension

The schema now permits a backward-compatible `structured_query` evidence item alongside existing plain-string labels. A structured item can record:

- the query language and parameterized query text
- the query engine version and source system
- a source snapshot identifier
- the time of the query
- the canonicalization method and a SHA-256 commitment to the result
- an optional protected reference to the full result artifact

This lets an auditor distinguish a descriptive evidence label from an evidence artifact with declared provenance and a tamper-evident result commitment. Mixed arrays are valid: use structured-query evidence where its re-checkability matters, without forcing every legacy evidence source into the same form.

The [loan-denial example](./case-study-loan-denial.md) shows this mixed form.

### What this does not do

This is **not** runtime re-verification. `dam_verify` does not hold a live connection to an AI query backend, automatically re-run stored queries, or block an action when a query answer changes.

A stored query alone is not enough for reproducibility. Later inspection depends on the query engine, access permissions, source snapshot, and canonical result artifact still being available. The `result_hash` commits to a canonical result representation; it does not place that result, potentially including sensitive evidence, in the public receipt.

A future `reverify_evidence()` capability would require an explicit backend adapter, protected artifact retrieval, source snapshot semantics, query-engine compatibility rules, and a policy decision about what a changed answer should do to a sealed receipt.

### Interoperability position

`structured_query` is vendor-neutral. SQL, AISQL, or another query language can be named in `query_language`; the Decision Receipt schema does not depend on a specific query vendor or claim equivalence between their semantics.
