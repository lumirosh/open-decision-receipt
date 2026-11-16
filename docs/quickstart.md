# Quickstart

Run the reference implementation locally and produce a sealed Decision Receipt.

## Install

Requires Python 3.11 or later. From a fresh checkout, install the project and development test dependency in your chosen Python environment, then run the tests:

```bash
git clone https://github.com/lumirosh/open-decision-receipt.git
cd open-decision-receipt
python -m pip install -e '.[dev]'
python -m pytest -q
```

## Verify an action

Use a temporary receipt store so the demo leaves no repo-local runtime state.

```bash
RECEIPTS_DIR="$(mktemp -d)"

dam-verify --receipts-dir "$RECEIPTS_DIR" \
  verify examples/verify-action-deploy.json
```

The first verdict should be `needs_human_review` because this is a high-risk deployment action.

Copy the `decision_id` from the verify output and set it below.

## Approve and seal

The approver and role are recorded and matched against the bundle's role assignment. This check does not authenticate the person using that name or prove they are the assigned person. `separation_of_duties_ok` is a recorded comparison with the requester; it is not a policy-enforced approval rule unless your integration checks it.

```bash
DECISION_ID="DR-YYYY-MM-DD-xxxxxx"

dam-verify --receipts-dir "$RECEIPTS_DIR" \
  approve "$DECISION_ID" --approver operator --approver-role change_authority

dam-verify --receipts-dir "$RECEIPTS_DIR" \
  seal "$DECISION_ID"
```

## Replay the receipt

```bash
dam-verify --receipts-dir "$RECEIPTS_DIR" \
  replay "$DECISION_ID"
```

Look for:

```text
check==use : True
```

That means the recorded check-time and execution-time evidence hashes matched. It does not establish that the evidence was true or independently observed.

## Verify the hash chain

```bash
dam-verify --receipts-dir "$RECEIPTS_DIR" chain
```

Expected:

```text
chain intact: True
```

## Compile a constrained action schema

```bash
dam-verify --receipts-dir "$RECEIPTS_DIR" \
  grammar "$DECISION_ID"
```

The output JSON Schema binds generation to:

- the exact approved action
- the exact `decision_id`
- the approved params

Unauthorized or action-unbound receipts produce no grammar. All three output fields are required. Additional parameter-schema constraints may narrow the approved params, never replace them or allow a different action.

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
dam-verify --receipts-dir "$RECEIPTS_DIR" watch
```

Expected:

```text
reopen_events: 1
parent=<sealed-parent-id> child=<revalidation-child-id>
```

The sealed parent remains immutable. The basis changed, so `watch` appends a
reopen event and creates a linked child in `needs_human_review`. Re-run verification
on that child before any new approval, action, or seal.
