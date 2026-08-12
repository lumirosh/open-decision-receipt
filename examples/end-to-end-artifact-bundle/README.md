# End-to-End Authority-to-Accountability Artifact Bundle

This illustrative certification-gated deployment demonstrates the narrow runnable profile:

```text
Authority basis
→ exact allow request
→ explicit approval
→ execution evidence
→ sealed parent receipt
→ authority-basis drift
→ append-only ReopenEvent
→ linked child lifecycle requiring revalidation
```

The same authority basis also evaluates an explicitly prohibited `bypass_gate` request and produces `refuse-receipt.json` without execution evidence.

## Files

- `authority-basis.yaml`: versioned authority rule and evidence basis.
- `allow-request.json`: exact request inside the allowed action set.
- `refuse-request.json`: exact request explicitly outside authority.
- `execution-evidence.json`: observed execution input used for sealing.
- `allow-sealed-receipt.json`: immutable parent receipt for the allowed path.
- `refuse-receipt.json`: fail-closed denied path.
- `reopen-event.json`: append-only event emitted after basis drift.
- `child-revalidation.json`: linked child lifecycle awaiting revalidation.
- `manifest.json`: relationship identifiers and SHA-256 hashes.

## Rebuild and verify

```bash
python3 scripts/build-end-to-end-artifact-bundle.py /tmp/odr-artifact-bundle
```

The builder requires an explicit output directory so it cannot silently overwrite
the committed example. Each run records fresh identifiers and timestamps; replay
means independently verifying that run's manifest and relationships, not producing
byte-identical artifacts.

```bash
python3 -m pytest -q tests/test_end_to_end_artifact_bundle.py
```

## Boundary

This bundle proves the behavior of the current local reference implementation. It does not prove a full enterprise Mandate Service, external key custody, cross-organization delegation, continuous mid-execution revocation, or independent third-party validation.
