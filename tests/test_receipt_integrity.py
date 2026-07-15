from dam_verify.receipt import ESCALATED, sha256_of


def test_sha256_of_returns_full_digest():
    digest = sha256_of({"decision": "synthetic"})
    assert digest.startswith("sha256:")
    assert len(digest.removeprefix("sha256:")) == 64


def test_escalated_is_a_distinct_terminal_review_state():
    assert ESCALATED == "escalated"
