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


def test_appraisal_resource_composition_observes_effects_not_just_seals():
    import json

    script = EXAMPLE.with_name('resource_probe.py')
    assert script.is_file(), 'Missing composed appraisal-to-resource experiment'
    result = subprocess.run([sys.executable, str(script)], cwd=ROOT,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    rows = json.loads(result.stdout)
    expected = {
        'valid': ('sealed', 1, 1),
        'wrong_appraisal': ('CHECK_HELD', 0, 0),
        'unbound_appraisal': ('sealed', 1, 1),
        'changed_action': ('RESOURCE_REFUSED', 1, 0),
        'source_before_gate': ('GATE_HELD', 0, 0),
        'bypass_gate': ('needs_human_review', 1, 1),
        'source_after_gate': ('needs_human_review', 1, 1),
        'resource_withdrawal': ('RESOURCE_REFUSED', 1, 0),
        'restored_basis': ('RESOURCE_REFUSED', 1, 0),
        'post_effect_change': ('needs_human_review', 1, 1),
        'false_appraisal': ('sealed', 1, 1),
        'repeat_grant': ('sealed', 2, 1),
    }
    assert {r['case']: (r['stage'], r['pay_calls'], len(r['effects'])) for r in rows} == expected
    for row in rows:
        assert row['cleanup_complete'] is True
        assert len(row['effects']) == int(row['resource_consumed'])
        if row['effects']:
            assert row['effects'][0]['action_hash'] == row['recorded_action_hash']
            assert row['effects'][0]['operation'] == row['receipt']['decision_id']
    by_name = {r['case']: r for r in rows}
    for name in ('changed_action', 'resource_withdrawal', 'restored_basis'):
        assert by_name[name]['resource_refusals'] == ['basis or action commitment changed']
    assert by_name['repeat_grant']['resource_refusals'] == ['grant consumed']
    assert by_name['source_after_gate']['gate'] == 'PASS'
    assert by_name['bypass_gate']['gate'] == 'HOLD'
    assert by_name['resource_withdrawal']['events'].index('resource_withdrawn') < by_name['resource_withdrawal']['events'].index('pay_attempted')
    assert by_name['post_effect_change']['events'].index('effect_committed') < by_name['post_effect_change']['events'].index('source_changed')


def test_resource_probe_closes_all_connections_before_completion(monkeypatch):
    import runpy
    import sqlite3
    import pytest

    module = runpy.run_path(str(EXAMPLE.with_name('resource_probe.py')))
    connect = sqlite3.connect
    opened = []

    def tracking_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, 'connect', tracking_connect)
    result = module['run_case']('valid')
    assert result['cleanup_complete'] is True
    try:
        for connection in opened:
            with pytest.raises(sqlite3.ProgrammingError, match='closed'):
                connection.execute('SELECT 1')
    finally:
        for connection in opened:
            connection.close()


def test_resource_probe_does_not_report_completion_if_cleanup_fails(monkeypatch):
    import runpy
    from contextlib import contextmanager
    import pytest

    module = runpy.run_path(str(EXAMPLE.with_name('resource_probe.py')))
    run_case = module['run_case']
    temporary_directory = module['TemporaryDirectory']
    paths = []

    @contextmanager
    def fail_after_cleanup(**kwargs):
        with temporary_directory(**kwargs) as directory:
            paths.append(Path(directory))
            yield directory
        raise RuntimeError('injected cleanup failure')

    monkeypatch.setitem(run_case.__globals__, 'TemporaryDirectory', fail_after_cleanup)
    with pytest.raises(RuntimeError, match='injected cleanup failure'):
        run_case('valid')
    assert paths and not paths[0].exists()
