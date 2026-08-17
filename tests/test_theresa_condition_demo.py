import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "theresa-condition-freshness-demo.py"


def test_theresa_scenario_runs_five_states_with_human_verdicts():
    run = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert run.returncode == 0, run.stderr
    output = run.stdout
    for heading in (
        "1. ALL HOLDING",
        "2. BREACHED",
        "3. STALE",
        "4. SCOPED REVALIDATION",
        "5. UNAPPROVED COMPENSATION",
    ):
        assert heading in output
    assert "VERDICT                      SEALED" in output
    assert "VERDICT                      PAUSED" in output
    assert "vendor-attestation (stale)" in output
    assert "REVALIDATION SCOPE           vendor-attestation" in output
    assert "VERDICT                      REFUSED" in output
    assert "BOUNDARY" in output
    assert "does not observe real-world effects" in output
