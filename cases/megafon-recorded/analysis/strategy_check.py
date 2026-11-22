"""Mechanical cross-checks complement, but do not replace, the semantic audit."""
import csv
import hashlib
import json
import math
import re
from pathlib import Path
from statistics import NormalDist

root=Path(__file__).resolve().parents[1]
claims=list(csv.DictReader((root/'claims.tsv').open(),delimiter='\t'))
active={r['id']:r for r in claims if r['status']=='active'}
audit=list(csv.DictReader((root/'audit.tsv').open(),delimiter='\t'))
fragments={r['locator']:r['text'] for r in map(json.loads,(root/'evidence/S-001@1.jsonl').read_text().splitlines())}
assert len(active)==41 and len(audit)==41
assert len({r['id'] for r in audit})==41 and {r['id'] for r in audit}==set(active)
assert all(r['verdict'] in ('supported','bounded') and len(r['rationale'])>70 for r in audit)
for row in active.values():
    if row['type']=='fact':
        assert row['source']=='S-001@1'
        assert row['quote'] in fragments[row['locator']]
    else:
        assert row['basis'] and all(x in active for x in row['basis'].split(','))
    assert row['scope']
refs=set(re.findall(r'\[\[(C-\d+)\]\]',(root/'strategy.md').read_text()))
assert refs<=set(active)
results=json.loads((root/'analysis/strategy_results.json').read_text())
params=json.loads((root/'analysis/strategy_parameters.json').read_text())
assert results['input_sha256']==hashlib.sha256((root/'analysis/strategy_parameters.json').read_bytes()).hexdigest()
assert results['research_auxiliary_hashes_all_match']
assert not results['full_rule_sample_justified']
sample=next(r for r in results['sample_sensitivity'] if r['control_risk']==.12 and r['true_benefit']==.03 and r['n_per_arm']==2000)
assert math.isclose(sample['prob_primary_rule'],.5,abs_tol=1e-12)
# Independent scalar checks against closed-form arithmetic, not imported calculator functions.
sd=math.sqrt((.12*.88+.09*.91)/2000)
power=NormalDist().cdf(.03/sd-NormalDist().inv_cdf(.975))
assert math.isclose(power,sample['power_vs_zero'],abs_tol=1e-12)
assert 0.87<power<.88
assert 1-.05**(1/2995)<=.001 and 1-.05**(1/2994)>.001
assert 2*12078==24156 and 24156/6==4026
assert sum([.5,.75,.75,.5,.5])==3
assert 2000*6*.1*500-300000==300000
assert 1000*3*.02*500-600000==-570000
assert 20000*6*.12*500-1000000==6200000
for row in results['sample_sensitivity']:
    assert 0<=row['covered_conjunction_lower']<=row['covered_conjunction_upper']<=1
    assert row['full_rule_lower']==0
report={'active_claims':len(active),'fact_quotes_checked':sum(r['type']=='fact' for r in active.values()),
        'audit_rows':len(audit),'strategy_claim_references':sorted(refs),
        'checks':'passed: quotes, basis IDs, scope, coverage, references, independent arithmetic, parameter hash',
        'semantic_review':'Manual in audit.tsv and quality.md; not inferred from these mechanical checks.',
        'primary_power_independent_check':power,'primary_full_threshold_check':.5,
        'full_rule_sample_justified':False,
        'source_dependency':'All 41 claims depend on the single educational S-001@1; no independent confirmation.'}
(root/'analysis/strategy_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
files=['strategy.md','audit.tsv','analysis/strategy_metrics.md','analysis/strategy_parameters.json',
       'analysis/strategy_calculate.py','analysis/strategy_check.py','analysis/strategy_results.json',
       'analysis/strategy_results.md','analysis/strategy_verification.json']
manifest={'algorithm':'sha256','purpose':'Strategy auxiliary reproducibility; quality.md records this manifest hash; CLI checkpoints strategy/quality/audit.',
          'files':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files}}
(root/'analysis/strategy_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
print('strategy_manifest_sha256='+hashlib.sha256((root/'analysis/strategy_manifest.json').read_bytes()).hexdigest())
