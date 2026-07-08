# Quickstart

Run the reference implementation locally and produce a sealed Decision Receipt.

## Install

```bash
git clone https://github.com/lumirosh/open-decision-receipt.git
cd open-decision-receipt
python -m pip install -e '.[dev]'
python -m pytest -q
```

## Verify an action

Use a temporary receipt store so the demo leaves no repo-local runtime state.

```bash
rm -rf /tmp/odr-receipts

dam-verify --receipts-dir /tmp/odr-receipts \
  verify examples/verify-action-deploy.json
```

The first verdict should be `needs_human_review` because this is a high-risk deployment action.

Capture the `decision_id` from the output.

## Approve and seal

```bash
DECISION_ID="DR-YYYY-MM-DD-xxxxxx"

dam-verify --receipts-dir /tmp/odr-receipts \
  approve "$DECISION_ID" --approver operator

dam-verify --receipts-dir /tmp/odr-receipts \
  seal "$DECISION_ID"
```

## Replay the receipt

```bash
dam-verify --receipts-dir /tmp/odr-receipts \
  replay "$DECISION_ID"
```

Look for:

```text
check==use : True
```

That means the evidence basis at execution matched the evidence basis at approval.

## Verify the hash chain

```bash
dam-verify --receipts-dir /tmp/odr-receipts chain
```

Expected:

```text
chain intact: True
```

## Compile a constrained action schema

```bash
dam-verify --receipts-dir /tmp/odr-receipts \
  grammar "$DECISION_ID"
```

The output JSON Schema binds generation to:

- the exact approved action
- the exact `decision_id`
- the approved params

Unauthorized receipts produce no grammar.

## Break the basis and watch it reopen

Edit `dam/action_bundles/cert_gated_deployment.yaml` in a throwaway branch or temp copy:

```yaml
evidence_sources:
  certification_status:
    version: 8
    content: "Certification CERT-2214 REVOKED. Scope invalidated."
```

Then run:

```bash
dam-verify --receipts-dir /tmp/odr-receipts watch
```

Expected:

```text
reopened: 1
```

The receipt was valid yesterday. The basis changed today. The same action now needs re-verification.
