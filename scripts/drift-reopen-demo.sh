#!/bin/bash
# Drift-reopen demo: 60-second proof that a sealed Decision Receipt
# reopens when its evidence basis changes.
#
# Run from the repo root. Creates receipts in a temp directory.
# Records the output for a screen-recording session.

set -euo pipefail
RECEIPTS=$(mktemp -d)
trap 'rm -rf "$RECEIPTS"' EXIT

say()  { echo ""; echo "=== $* ==="; }
cmd()  { echo ""; echo "> $*"; "$@"; }

say "01 — Verify a proposed action"
cmd dam-verify --receipts-dir "$RECEIPTS" verify examples/verify-action-deploy.json

say "02 — Human signs scoped authority"
ID=$(ls "$RECEIPTS" | head -1 | sed 's/\.json//')
cmd dam-verify --receipts-dir "$RECEIPTS" approve "$ID" --approver operator

say "03 — Seal (check-time equals use-time)"
cmd dam-verify --receipts-dir "$RECEIPTS" seal "$ID"

say "04 — The receipt is sealed"
cmd dam-verify --receipts-dir "$RECEIPTS" replay "$ID"

say "05 — Break the evidence basis: revoke the certificate"
cp dam/action_bundles/cert_gated_deployment.yaml /tmp/cert_gated_deployment_backup.yaml
cat > dam/action_bundles/cert_gated_deployment.yaml <<'BUNDLE'
workflow: cert_gated_deployment
version: 8
authority_rules:
  - actors: [release_workflow]
    risk_classes: [high]
    allowed_actions: [deploy_certified_workflow]
    denied_actions: [modify_certification, bypass_gate]
    requires_human: true
    basis: "runbook://cert-gated-deployment#v4"
    required_evidence: [certification_status]
evidence_sources:
  certification_status:
    version: 8
    content: "Certification CERT-2214 REVOKED. Scope invalidated."
BUNDLE
echo "Changed certification_status: version 8, content: REVOKED"

say "06 — Watch: the sealed receipt reopens"
cmd dam-verify --receipts-dir "$RECEIPTS" watch

say "07 — Same actor, same action, same workflow. Valid yesterday, blocked today."
mv /tmp/cert_gated_deployment_backup.yaml dam/action_bundles/cert_gated_deployment.yaml
