"""Authority bundles must remain inside their configured directory."""
import pytest

from dam_verify.engine import BundleStore


@pytest.mark.parametrize("route", ["relative", "absolute", "symlink"])
def test_bundle_store_refuses_outside_policy_files(tmp_path, route):
    root = tmp_path / "bundles"
    root.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_text("workflow: outside\nversion: 1\nauthority_rules: []\n")
    if route == "relative":
        workflow = "../outside"
    elif route == "absolute":
        workflow = str(outside.with_suffix(""))
    else:
        (root / "linked.yaml").symlink_to(outside)
        workflow = "linked"
    assert BundleStore(root).resolve(workflow) is None


def test_bundle_store_still_reads_its_own_policy(tmp_path):
    (tmp_path / "inside.yaml").write_text("workflow: inside\nversion: 1\n")
    assert BundleStore(tmp_path).resolve("inside") == {"workflow": "inside", "version": 1}
