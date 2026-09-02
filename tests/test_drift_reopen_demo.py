import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_drift_reopen_demo_completes():
    result = subprocess.run(
        ["bash", "scripts/drift-reopen-demo.sh"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Valid yesterday, blocked today" in result.stdout
