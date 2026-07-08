# Security Policy

Open Decision Receipt is an accountability artifact for high-consequence workflows. Treat examples and issues accordingly.

## Do not publish sensitive workflow data

Do not open public issues or pull requests containing:

- real secrets, API keys, tokens, session IDs, or private keys
- live customer, patient, employee, claimant, or financial records
- confidential workflow logs, prompts, model outputs, or incident evidence
- non-public security incidents or vulnerability details

Use sanitized examples. Replace real actors with roles, real IDs with placeholders, and real evidence with minimal reproductions.

## Reporting vulnerabilities

If you find a security issue in the reference implementation, report it privately through GitHub security advisories when available. If that is unavailable, contact the maintainers through the repository owner profile.

Please include:

- affected file and version or commit
- reproduction steps using sanitized data
- expected vs actual behavior
- impact on receipt integrity, replayability, authority checks, or chain verification

## Scope

In scope:

- receipt integrity/hash-chain bugs
- schema validation gaps that permit misleading receipts
- CLI behavior that silently fails open
- example or documentation patterns that encourage unsafe handling of secrets or private records

Out of scope:

- claims that Decision Receipts replace runtime enforcement
- legal/compliance advice requests
- vulnerabilities in third-party systems mentioned by examples

## Design posture

This project should fail closed. Unknown authority, missing evidence, or changed basis should block, deny, or require human review. A transaction log is not authorization proof.
