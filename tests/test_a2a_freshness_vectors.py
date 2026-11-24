"""Acceptance oracle for the local, synthetic A2A-inspired freshness fixture."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_a2a_freshness_vectors():
    run = subprocess.run(
        [sys.executable, str(ROOT / "examples/a2a_freshness_vectors.py"), "--json"],
        cwd=ROOT, capture_output=True, text=True, timeout=15,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert run.returncode == 0, run.stdout + run.stderr
    report = json.loads(run.stdout)
    assert report["scope"] == "local synthetic fixture; not A2A conformance"
    cases = {case["case"]: case for case in report["cases"]}
    expected = {
        "fresh": ("allow", "primary", 1),
        "exact_age_limit": ("allow", "primary", 1),
        "refetched_old": ("hold", None, 0),
        "new_observation_same_status": ("allow", "primary", 1),
        "age_unknown": ("hold", None, 0),
        "future_observation": ("hold", None, 0),
        "revoked": ("hold", None, 0),
        "fresh_alternative": ("allow", "alternative", 1),
        "unrelated_caller": ("hold", None, 0),
        "unrelated_delegate": ("hold", None, 0),
        "unrelated_task": ("hold", None, 0),
        "unrelated_context": ("hold", None, 0),
        "unrelated_target": ("hold", None, 0),
        "two_fresh_paths": ("allow", "primary", 1),
    }
    assert len(report["cases"]) == len(cases) == len(expected)
    assert set(cases) == set(expected)
    for name, wanted in expected.items():
        case = cases[name]
        assert (case["disposition"], case["chosen_path"], len(case["dispatch_log"])) == wanted, name
        assert all(effect == report["binding"] for effect in case["dispatch_log"]), name
    old = cases["refetched_old"]["paths"][0]
    assert old["as_of"] == "2026-11-24T10:00:00Z"
    assert old["retrieved_at"] == "2026-11-24T10:01:30Z"
    assert old["condition_check"]["aggregate"] == "stale"
    assert cases["age_unknown"]["paths"][0]["condition_check"]["aggregate"] == "unknown"
    assert cases["future_observation"]["paths"][0]["condition_check"]["aggregate"] == "unknown"
    assert cases["revoked"]["paths"][0]["condition_check"]["aggregate"] == "breached"
    fresh = cases["new_observation_same_status"]["paths"][0]
    assert fresh["as_of"] == "2026-11-24T10:01:20Z"
    assert fresh["evidence_ref"] != old["evidence_ref"]
    assert cases["fresh_alternative"]["paths"][0]["condition_check"]["aggregate"] == "stale"
    for name in [key for key in cases if key.startswith("unrelated_")]:
        alternative = cases[name]["paths"][1]
        assert alternative["condition_check"]["holds"] is True
        assert alternative["binding_matches"] is False
