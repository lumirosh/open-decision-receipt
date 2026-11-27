"""Exercise the documented appraisal example and the existing clock boundary."""
import subprocess
import sys
from pathlib import Path

from dam_verify.conditions import HOLDING, UNKNOWN, evaluate_condition

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples' / 'appraisal-binding' / 'probe.py'


def test_appraisal_example_keeps_exposing_controls_and_external_gate():
    assert EXAMPLE.is_file(), 'Missing eight-case appraisal integration example'
    result = subprocess.run([sys.executable, str(EXAMPLE)], cwd=ROOT,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '8 source-derived expectations matched; no real effect tested.' in result.stdout
    assert 'EXPOSED: same boolean appraisal reused for another action: sealed' in result.stdout
    assert 'EXPOSED: stored expected digest alone not linked to requested action: sealed' in result.stdout
    assert 'external gate checks appraisal/action correspondence: GATE_HELD' in result.stdout


def test_subsecond_future_observation_is_unknown_not_a_freshness_exception():
    definition = {'operator': 'eq', 'expected_value': 'ALLOW', 'max_age_seconds': 1}
    observation = {'observed_value': 'ALLOW',
                   'last_validated_at': '2026-11-27T11:00:00.500000+00:00'}
    assert evaluate_condition(definition, observation, '2026-11-27T11:00:00+00:00') == UNKNOWN
    assert evaluate_condition(definition, observation, '2026-11-27T11:00:00.600000+00:00') == HOLDING
