"""Compose the existing appraisal fixture with the local SQLite effect resource.

Twelve controlled schedules, not a real provider, issuer or concurrency proof.
The source observation and resource basis are separate trusted fixture inputs.
"""
import json
import runpy
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

fixture = runpy.run_path(str(Path(__file__).with_name('probe.py')))
A, B = fixture['A'], fixture['B']
WORKFLOW, ACTION = fixture['WORKFLOW'], fixture['ACTION']
prepare = fixture['prepare']

from dam_verify.conditions import evaluate_conditions
from dam_verify.engine import approve, canonical_action, seal
from dam_verify.receipt import now_iso, sha256_of
from integrations.authority_continuity import reference as resource

# ponytail: controlled single-process schedules; add concurrency proof only for that claim.
CASES = (
    'valid', 'wrong_appraisal', 'unbound_appraisal', 'changed_action',
    'source_before_gate', 'bypass_gate', 'source_after_gate',
    'resource_withdrawal', 'restored_basis', 'post_effect_change',
    'false_appraisal', 'repeat_grant',
)


def run_case(name):
    if name not in CASES:
        raise ValueError('unknown controlled scenario')
    events, refusals, pay_calls = [], [], 0
    params = B if name in {'wrong_appraisal', 'unbound_appraisal', 'false_appraisal'} else A
    action = canonical_action(WORKFLOW, ACTION, params)
    digest_a = sha256_of(canonical_action(WORKFLOW, ACTION, A))
    expected = digest_a if name == 'unbound_appraisal' else sha256_of(action)
    observed = sha256_of(action) if name == 'false_appraisal' else digest_a
    with TemporaryDirectory(prefix='odr-appraisal-resource-') as directory:
        root = Path(directory)
        receipt, bundles, observations, write = prepare(root, params, expected, observed)
        events.append('appraisal_checked')
        db = root / 'resource.sqlite'
        stage, gate = 'CHECK_HELD', 'NOT_REACHED'
        if not receipt.check.get('failed_conditions') and not receipt.check.get('missing'):
            approve(receipt, 'reviewer-1', bundles, 'reviewer')
            events.append('synthetic_approval')
            resource.register(db, receipt, 1, 'basis-v1', 'worker', 1)
            events.append('grant_registered')
            if name in {'source_before_gate', 'bypass_gate'}:
                write('REVOKED')
                events.append('source_changed')
            definitions = bundles.resolve(WORKFLOW)['conditions']
            current = evaluate_conditions(definitions,
                observations.observations_for(WORKFLOW, ['appraisal']), now_iso())
            gate = 'PASS' if current['holds'] else 'HOLD'
            events.append('gate_' + gate.lower())
            stage = 'GATE_HELD'
            if current['holds'] or name == 'bypass_gate':
                if name == 'source_after_gate':
                    write('REVOKED')
                    events.append('source_changed')
                if name in {'resource_withdrawal', 'restored_basis'}:
                    # Publish the stricter resource state before changing the source view.
                    resource.set_basis(db, 2, 'withdrawn', False)
                    events.append('resource_withdrawn')
                    if name == 'restored_basis':
                        resource.set_basis(db, 3, 'basis-v1', True)
                        events.append('resource_reactivated_new_generation')
                    write('REVOKED' if name == 'resource_withdrawal' else observed)
                    events.append('source_changed')
                submitted = canonical_action(WORKFLOW, ACTION, B) if name == 'changed_action' else action
                pay_calls += 1
                events.append('pay_attempted')
                try:
                    resource.pay(db, receipt.decision_id, submitted, 'worker', 1)
                except ValueError as exc:
                    refusals.append(str(exc))
                    events.append('resource_refused')
                    stage = 'RESOURCE_REFUSED'
                else:
                    events.append('effect_committed')
                    if name == 'post_effect_change':
                        resource.set_basis(db, 2, 'withdrawn', False)
                        events.append('resource_withdrawn')
                        write('REVOKED')
                        events.append('source_changed')
                    # Read the native effect commitment and its registered payload back.
                    # This observes a trusted local resource, not an independent PSP.
                    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as conn:
                        stored, effect_hash = conn.execute(
                            'SELECT g.action,e.action_hash FROM grants g JOIN effects e '
                            'ON g.operation=e.operation WHERE g.operation=?',
                            (receipt.decision_id,)).fetchone()
                    recorded_action = json.loads(stored)
                    assert sha256_of(recorded_action) == effect_hash
                    seal(receipt, {'canonical_action': recorded_action,
                                   'execution_result': 'synthetic-local-sqlite-effect'},
                         bundles, observations)
                    stage = receipt.status
                    events.append('seal_' + stage)
                    if name == 'repeat_grant':
                        pay_calls += 1
                        events.append('pay_attempted')
                        try:
                            resource.pay(db, receipt.decision_id, submitted, 'worker', 1)
                        except ValueError as exc:
                            refusals.append(str(exc))
                            events.append('resource_refused')
        effects, consumed, basis = [], False, None
        if db.exists():
            with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as conn:
                effects = [dict(zip(('operation', 'action_hash', 'owner'), row))
                           for row in conn.execute('SELECT operation,action_hash,owner FROM effects')]
                row = conn.execute('SELECT consumed FROM grants WHERE operation=?',
                                   (receipt.decision_id,)).fetchone()
                consumed = bool(row and row[0])
                basis = conn.execute('SELECT generation,snapshot,enabled FROM basis').fetchone()
        result = {'case': name, 'stage': stage, 'gate': gate, 'pay_calls': pay_calls,
                  'resource_refusals': refusals, 'effects': effects,
                  'resource_consumed': consumed, 'resource_basis': basis,
                  'recorded_action_hash': receipt.request['action_hash'],
                  'appraisal_observed': observed, 'appraisal_expected': expected,
                  'events': events, 'receipt': receipt.to_dict()}
        if name in {'unbound_appraisal', 'false_appraisal'}:
            # Deliberately false/unsupported evidence: this oracle is NOT a gate input.
            result['truth_oracle_only'] = canonical_action(WORKFLOW, ACTION, A)
    # Never report completion before temporary-resource cleanup has succeeded.
    result['cleanup_complete'] = True
    return result


if __name__ == '__main__':
    print(json.dumps([run_case(name) for name in CASES], indent=2))
