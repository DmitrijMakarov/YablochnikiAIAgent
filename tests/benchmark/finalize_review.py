"""Verify source immutability and seal review artifacts (not a new model run)."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from archive_results import OUT, HERE, ROOT, inventory, verify

manifest=verify()
result={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'sources':{},'registered':{},'broken_local_links':[]}
for mode,run in manifest['runs'].items():
    original=inventory(Path(run['source']))
    expected={rel:{key:entry[key] for key in ('sha256','bytes')} for rel,entry in run['files'].items()}
    result['sources'][mode]={'files':len(original),'equal_sealed_inventory':original==expected}
    assert original==expected
for rel,expected in json.loads((HERE/'registration.json').read_text())['files_sha256'].items():
    result['registered'][rel]=hashlib.sha256((HERE/rel).read_bytes()).hexdigest()==expected
assert all(result['registered'].values())
report=HERE/'comparison-report.md'
for href in re.findall(r'\]\(([^)]+)\)',report.read_text()):
    if not href.startswith(('http:','https:')) and not (HERE/href).exists() and href not in ('results/final-integrity.json','results/SHA256SUMS'):
        result['broken_local_links'].append(href)
assert not result['broken_local_links']
result['report_sha256']=hashlib.sha256(report.read_bytes()).hexdigest()
(OUT/'final-integrity.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
scores=[]
for criterion,a,b in re.findall(r'^\| (E\d+)\. [^|]+\| (\d) \| (\d) \|$',report.read_text(),re.M):
    scores.extend([f'A\t{criterion}\t{a}',f'B\t{criterion}\t{b}'])
assert len(scores)==20
(OUT/'expert-scores.tsv').write_text('mode\tcriterion\tscore\n'+'\n'.join(scores)+'\n')
paths=[p for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256SUMS']
paths += [HERE/name for name in ('comparison-report.md','archive_results.py','compare_checks.py','prepare_review.py','reproduce_review.py','finalize_review.py')]
lines=[hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(HERE)) for p in sorted(paths)]
(OUT/'SHA256SUMS').write_text('\n'.join(lines)+'\n')
print(json.dumps({'source_checks':result['sources'],'checksummed_files':len(paths),'scores':len(scores),'broken_links':result['broken_local_links']},ensure_ascii=False,indent=2))
