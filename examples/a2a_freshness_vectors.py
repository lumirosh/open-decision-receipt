#!/usr/bin/env python3
"""Local A2A-inspired vectors. Trusted fixture inputs, not an A2A adapter."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dam_verify.conditions import evaluate_conditions
from dam_verify.engine import canonical_action

BINDING = {
    "caller": "requester-A", "delegate": "agent-B",
    "task": "release-17", "context": "project-4",
    "effect": canonical_action("fixture_release", "update_display_name", {
        "resource": "settings.json", "display_name": "Release",
    }),
}
AS_OF = "2026-11-24T10:00:00Z"
LATER = "2026-11-24T10:01:30Z"


def assess(binding, paths, decision_at, dispatch):
    """Check each declared path independently, then invoke one local callback."""
    checks = []
    chosen = None
    for path in paths:
        observation = path["observation"]
        source = path["source_ref"]
        result = evaluate_conditions(
            [{"condition_id": "upstream-active", "source_ref": source,
              "operator": "eq", "expected_value": "ACTIVE", "max_age_seconds": 60}],
            {source: {"observed_value": observation["status"],
                      "last_validated_at": observation["as_of"]}},
            decision_at,
        )
        binding_matches = path["binding"] == binding
        checks.append({
            "path_id": path["path_id"], "binding_matches": binding_matches,
            "source_ref": source, "evidence_ref": observation["evidence_ref"],
            "as_of": observation["as_of"], "retrieved_at": observation["retrieved_at"],
            "condition_check": result,
        })
        if chosen is None and binding_matches and result["holds"]:
            chosen = path["path_id"]
    if chosen is not None:
        dispatch(deepcopy(binding))
    return {"decision_at": decision_at, "disposition": "allow" if chosen else "hold",
            "chosen_path": chosen, "paths": checks}


def run_vectors():
    primary = {
        "path_id": "primary", "binding": deepcopy(BINDING),
        "source_ref": "fixture://issuer-A/upstream-grant",
        "observation": {"status": "ACTIVE", "as_of": AS_OF,
                        "retrieved_at": "2026-11-24T10:00:30Z",
                        "evidence_ref": "fixture://issuer-A/observation-1"},
    }
    stale = deepcopy(primary)
    stale["observation"]["retrieved_at"] = LATER
    fresh = deepcopy(stale)
    fresh["observation"].update(
        as_of="2026-11-24T10:01:20Z", evidence_ref="fixture://issuer-A/observation-2")
    unknown = deepcopy(stale)
    unknown["observation"]["as_of"] = None
    future = deepcopy(stale)
    future["observation"]["as_of"] = "2026-11-24T10:02:00Z"
    revoked = deepcopy(fresh)
    revoked["observation"]["status"] = "REVOKED"
    alternative = deepcopy(fresh)
    alternative["path_id"] = "alternative"
    alternative["source_ref"] = "fixture://issuer-C/independent-grant"
    alternative["observation"]["evidence_ref"] = "fixture://issuer-C/observation-1"
    cases = [
        ("fresh", "2026-11-24T10:00:30Z", [primary]),
        ("exact_age_limit", "2026-11-24T10:01:00Z", [primary]),
        ("refetched_old", LATER, [stale]),
        ("new_observation_same_status", LATER, [fresh]),
        ("age_unknown", LATER, [unknown]),
        ("future_observation", LATER, [future]),
        ("revoked", LATER, [revoked]),
        ("fresh_alternative", LATER, [stale, alternative]),
    ]
    for member in ("caller", "delegate", "task", "context"):
        unrelated = deepcopy(alternative)
        unrelated["binding"][member] = "unrelated"
        cases.append(("unrelated_" + member, LATER, [stale, unrelated]))
    unrelated = deepcopy(alternative)
    unrelated["binding"]["effect"]["parameters"]["resource"] = "other.json"
    cases.append(("unrelated_target", LATER, [stale, unrelated]))
    cases.append(("two_fresh_paths", LATER, [fresh, alternative]))
    results = []
    for name, decision_at, paths in cases:
        dispatch_log = []
        result = assess(BINDING, paths, decision_at, dispatch_log.append)
        results.append({"case": name, **result, "dispatch_log": dispatch_log})
    return {
        "scope": "local synthetic fixture; not A2A conformance", "binding": BINDING,
        "assumptions": [
            "Caller, delegate, task/context binding, independent grants and source provenance are trusted fixture inputs, not authenticated here.",
            "last_validated_at is mapped from the asserted trusted source as-of time, never from retrieval time.",
            "A changed evidence reference/time asserts a new authoritative observation; this fixture does not prove the source made it.",
            "Dispatch is a local list append. No network, A2A transport, external effects, cryptography, chain resolution or revocation-propagation measurement.",
            "Selecting one path in one invocation is not durable idempotency, concurrency safety or exactly-once execution.",
        ],
        "cases": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit full source-backed local assessment records")
    args = parser.parse_args()
    report = run_vectors()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(report["scope"])
        for case in report["cases"]:
            print(f"{case['case']}: {case['disposition'].upper()} path={case['chosen_path']} dispatches={len(case['dispatch_log'])}")
        print("These are observed local results; run tests/test_a2a_freshness_vectors.py for the independent acceptance oracle.")
