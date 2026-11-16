"""Check canonical resources and the installed wheel, outside the checkout.

Install the supplied wheel into this interpreter before running this check.
"""
import json
import os
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = [
    "schemas/decision-receipt.schema.json",
    "schemas/action-request.schema.json",
    "schemas/reopen-event.schema.json",
    "dam/action_bundles/cert_gated_deployment.yaml",
    "dam/action_bundles/soc_automated_containment.yaml",
]


def main(wheel, sdist):
    python_sources = sorted(path for package in ("dam_verify", "integrations")
                            for path in (ROOT / package).rglob("*.py"))
    with zipfile.ZipFile(wheel) as archive:
        for source in python_sources:
            assert archive.read(source.relative_to(ROOT).as_posix()) == source.read_bytes(), source
        for resource in RESOURCES:
            packaged = "dam_verify/_resources/" + resource.removeprefix("dam/")
            assert archive.read(packaged) == (ROOT / resource).read_bytes(), packaged
    with tarfile.open(sdist) as archive:
        prefix = Path(archive.getnames()[0]).parts[0]
        for resource in RESOURCES:
            member = archive.extractfile(f"{prefix}/{resource}")
            assert member is not None, resource
            with member:
                assert member.read() == (ROOT / resource).read_bytes(), resource
    with tempfile.TemporaryDirectory() as temp:
        outside = Path(temp)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        origin = subprocess.check_output(
            [sys.executable, "-c", "import dam_verify; print(dam_verify.__file__)"],
            cwd=outside, env=env, text=True,
        ).strip()
        assert not Path(origin).resolve().is_relative_to(ROOT), "install the wheel, not an editable checkout"
        installed_root = Path(origin).resolve().parent.parent
        for source in python_sources:
            assert (installed_root / source.relative_to(ROOT)).read_bytes() == source.read_bytes(), source
        entry = Path(sysconfig.get_path("scripts")) / ("dam-verify.exe" if os.name == "nt" else "dam-verify")
        assert entry.is_file(), "installed console entry point is missing"

        def cli(*arguments):
            return subprocess.check_output([str(entry), *arguments], cwd=outside, env=env, text=True)

        assert "PASS: schema valid" in cli("validate", str(ROOT / "examples/loan-denial-receipt.yaml"))
        verified = json.loads(cli("verify", str(ROOT / "examples/verify-action-deploy.json")))
        assert verified["status"] == "needs_human_review"
        decision = verified["decision_id"]
        approved = json.loads(cli("approve", decision, "--approver", "operator", "--approver-role", "change_authority"))
        assert approved["status"] == "authorized"
        sealed = json.loads(cli("seal", decision))
        assert sealed["status"] == "sealed"
        assert "check==use : True" in cli("replay", decision)
        grammar = json.loads(cli("grammar", decision))
        assert set(grammar["required"]) == {"action", "decision_id", "params"}
        request = json.loads((ROOT / "examples/verify-action-deploy.json").read_text())
        assert grammar["properties"]["params"]["const"] == request["params"]
        assert "chain intact: True" in cli("chain")
        assert "reopen_events: 0" in cli("watch")
        receipt = outside / "data" / "action_receipts" / (decision + ".json")
        assert receipt.is_file(), "default receipts must be in caller's working directory"
        assert "PASS: schema valid" in cli("validate", str(receipt))
        promoted = outside / "dam" / "bundles"
        assert "DRY RUN" in cli("promote", decision)
        assert not promoted.exists()
        assert "Promoted receipt" in cli("promote", decision, "--approve")
        assert len(list(promoted.rglob("*.md"))) == 1
        module = subprocess.check_output(
            [sys.executable, "-m", "integrations.authority_continuity.reference"],
            cwd=outside, env=env, text=True,
        )
        assert json.loads(module)["effects"] == 1
        assert not (Path(origin).resolve().parent.parent / "data" / "action_receipts").exists()
        assert not (installed_root / "dam" / "bundles").exists()
        print(json.dumps({"packaging_smoke": "PASS", "canonical_resources": len(RESOURCES),
                          "python_source_files_matched": len(python_sources), "grammar_required": grammar["required"],
                          "console_lifecycle": "verify/approve/seal/replay/grammar/chain/watch/validate/promote",
                          "adapter_demo": "PASS", "default_output": "caller working directory"}))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: packaging_smoke.py WHEEL SDIST")
    main(*sys.argv[1:])
