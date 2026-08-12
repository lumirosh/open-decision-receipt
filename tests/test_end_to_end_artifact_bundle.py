import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-end-to-end-artifact-bundle.py"


def test_build_end_to_end_artifact_bundle(tmp_path):
    subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], cwd=ROOT, check=True)

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    parent = json.loads((tmp_path / "allow-sealed-receipt.json").read_text())
    refused = json.loads((tmp_path / "refuse-receipt.json").read_text())
    event = json.loads((tmp_path / "reopen-event.json").read_text())
    child = json.loads((tmp_path / "child-revalidation.json").read_text())

    assert parent["status"] == "sealed"
    assert refused["status"] == "denied"
    assert event["parent_receipt_id"] == parent["decision_id"]
    assert child["parent_receipt_id"] == parent["decision_id"]
    assert child["reopen_event_id"] == event["event_id"]
    assert manifest["relationships"]["sealed_parent"] == parent["decision_id"]
    assert manifest["relationships"]["reopen_event"] == event["event_id"]
    assert set(manifest["sha256"]) == {
        "authority-basis.yaml",
        "allow-request.json",
        "refuse-request.json",
        "execution-evidence.json",
        "allow-sealed-receipt.json",
        "refuse-receipt.json",
        "reopen-event.json",
        "child-revalidation.json",
    }


def test_builder_requires_explicit_output_directory():
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT, capture_output=True, text=True)

    assert result.returncode != 0
    assert "OUTPUT_DIR" in result.stderr
