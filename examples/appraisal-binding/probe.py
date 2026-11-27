"""External synthetic research harness for ODR rc4 APIs; no repo edits or real effects.
Run from the checkout: python examples/appraisal-binding/probe.py
Eight synthetic cases; generic verdicts are deliberate exposing controls.
Observation fixtures use whole seconds to match the default evaluation clock.
The external gate checks only action correspondence, not source legitimacy.
No actual payment or independent source attestation. Seal receives mock executor record.
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime,timezone
import sys

# Run this checkout, never silently use a different installed ODR revision.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from dam_verify.engine import BundleStore, verify_action, approve, seal, canonical_action
    from dam_verify.conditions import ObservationsStore
    from dam_verify.receipt import sha256_of
except ModuleNotFoundError as e:
    raise SystemExit(f'NOT RUN: ODR dependency not available: {e}')

WORKFLOW='appraisal_probe'
ACTION='pay_synthetic'
A={'obligation':'invoice-7','entity':'supplier-7','amount':100,'currency':'USD','account':'account-A'}
B=A|{'account':'account-B'}

def prepare(root, params, condition, observed):
    """Shared temporary fixture for the mock-seal and resource experiments."""
    root = Path(root)
    bundles, obs = root / 'bundles', root / 'obs'
    bundles.mkdir()
    obs.mkdir()
    bundle = {
        'workflow': WORKFLOW, 'version': 1,
        'human_gate': {'allowed_roles': ['reviewer'],
                       'role_assignments': {'reviewer': ['reviewer-1']}},
        'authority_rules': [{'actors': ['agent'], 'risk_classes': ['high'],
                             'allowed_actions': [ACTION], 'denied_actions': [],
                             'requires_human': True, 'basis': 'synthetic review rule'}],
    }
    if condition is not None:
        bundle['conditions'] = [{'condition_id': 'source-appraisal',
                                 'source_ref': 'appraisal', 'operator': 'eq',
                                 'expected_value': condition, 'max_age_seconds': 300}]
    (bundles / f'{WORKFLOW}.yaml').write_text(json.dumps(bundle))

    def write(value):
        snapshots = {} if value is None else {'appraisal': {
            'observed_value': value,
            'last_validated_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}}
        (obs / f'{WORKFLOW}.yaml').write_text(json.dumps({'observations': snapshots}))

    write(observed)
    bs, observations = BundleStore(bundles), ObservationsStore(obs)
    request = {'workflow': WORKFLOW, 'actor': 'agent', 'risk_class': 'high',
               'action': ACTION, 'params': params}
    return verify_action(request, bs, observations), bs, observations, write


def run(case,params,condition,observed,post=None,qualified_gate=False):
    with TemporaryDirectory() as d:
        r, bs, observations, write = prepare(d, params, condition, observed)
        if r.check.get('failed_conditions') or r.check.get('missing'):
            return 'CHECK_HELD'
        approve(r,'reviewer-1',bs,'reviewer')
        if qualified_gate and observed!=sha256_of(canonical_action(WORKFLOW,ACTION,params)):
            return 'GATE_HELD'
        if post is not None: write(post)
        # This is a supplied synthetic execution record, not a resource effect.
        r=seal(r,{'canonical_action':r.request['canonical_action'],'execution_result':'synthetic'},bs,observations)
        return r.status

if __name__=='__main__':
    a_hash=sha256_of(canonical_action(WORKFLOW,ACTION,A))
    rows=[
        ('exact approved action, no source condition',B,None,None,None,False,'sealed'),
        ('honest boolean appraisal',A,'ALLOW','ALLOW',None,False,'sealed'),
        ('EXPOSED: same boolean appraisal reused for another action',B,'ALLOW','ALLOW',None,False,'sealed'),
        ('missing appraisal',A,'ALLOW',None,None,False,'CHECK_HELD'),
        ('appraisal changes before mock seal',A,'ALLOW','ALLOW','REVOKED',False,'needs_human_review'),
        ('EXPOSED: stored expected digest alone not linked to requested action',B,a_hash,a_hash,None,False,'sealed'),
        ('external gate checks appraisal/action correspondence',B,a_hash,a_hash,None,True,'GATE_HELD'),
        ('matching exact appraisal at external gate',A,a_hash,a_hash,None,True,'sealed'),
    ]
    for case,*args,expected in rows:
        result=run(case,*args)
        print(f'{case}: {result} (expected {expected})')
        assert result==expected,(case,result,expected)
    print(f'{len(rows)} source-derived expectations matched; no real effect tested.')
