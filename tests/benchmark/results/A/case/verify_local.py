#!/usr/bin/env python3
"""Independent data reconciliation and integrity checks; no network, no packages."""
import csv,json,hashlib,math,re
from pathlib import Path
from datetime import datetime,timezone,date,timedelta
from collections import defaultdict
P=Path(__file__).resolve().parent;ROOT=P.parent;C=P/'calculations'
def read(p,delimiter=','):
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f,delimiter=delimiter))
# Recreate the explicit prospective guardrail planning scenario.
guard_n=math.ceil(2*.47*.53*((1.644853626951+.841621233573)/.02)**2)
guard=dict(metric='early_completion_D0_2',baseline_assumed=.47,noninferiority_margin_absolute=.02,true_difference_assumed=0,alpha_one_sided=.05,power=.8,n_per_arm_approx=guard_n,total=2*guard_n,weeks_enrollment_at_300=2*guard_n/300,scope='overall only; subgroup and opt-out/complaint baselines need separate planning')
with (C/'guardrail_sample_size.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(guard));w.writeheader();w.writerow(guard)
checks=[]
def check(name,value):
 assert value,name
 checks.append(name)
versions=json.loads((P/'input_versions.json').read_text())
for path,meta in versions.items():
 f=ROOT/path;check('input integrity '+path,hashlib.sha256(f.read_bytes()).hexdigest()==meta['sha256'])
check('brief equals original',(P/'brief.md').read_bytes()==(ROOT/'SOURCE_BRIEF.md').read_bytes())
manifest=json.loads((P/'inputs.json').read_text());reg=read(P/'source_registry.tsv','\t')
check('all 7 approved sources registered',{r['source_id'] for r in reg}=={r['id'] for r in manifest['sources']} and len(reg)==7)
for r in reg:check('registry hash '+r['source_id'],hashlib.sha256((ROOT/r['local_file']).read_bytes()).hexdigest()==r['sha256'])
s=read(P/'inputs/signups.csv');e=read(P/'inputs/events.csv');cov=read(P/'inputs/coverage.csv');complete={(r['event_date'],r['platform']) for r in cov if r['status']=='complete'}
# Independent target-date membership algorithm; does not import the analysis implementation.
completed={(r['user_id'],r['event_date']) for r in e if r['event_type']=='task_completed'}
opened={(r['user_id'],r['event_date']) for r in e if r['event_type']=='app_open'}
weeks=sorted({r['cohort_week'] for r in s});periods={'early_3':weeks[:3],'later_3':weeks[3:6],'recent_3':weeks[6:9],'all_common_6':weeks[:6],'all_D7_9':weeks[:9]}
period=read(C/'periods.csv');cohorts=read(C/'cohorts.csv')
for out in [*period,*cohorts]:
 metric=out['metric']
 if metric not in ['D7_completed','D30_completed','D7_open','D30_open','D6_8_completed','D28_32_completed','D1_7_completed','D24_30_completed']:continue
 m=re.fullmatch(r'D(\d+)(?:_(\d+))?_(completed|open)',metric);a=int(m[1]);b=int(m[2] or m[1]);data=opened if m[3]=='open' else completed
 pop=[r for r in s if r['cohort_week'] in (periods[out['period']] if 'period' in out else [out['cohort_week']])]
 n=k=0
 for u in pop:
  d=date.fromisoformat(u['signup_date']);days=[(d+timedelta(days=x)).isoformat() for x in range(a,b+1)]
  if all((day,u['platform']) in complete for day in days):
   n+=1;k+=any((u['user_id'],day) in data for day in days)
 label=(out.get('period') or out.get('cohort_week'))+' '+metric
 check('independent numerator/denominator '+label,n==int(out['n']) and k==int(out['k']))
 if n:check('ratio '+label,abs(float(out['rate'])-k/n)<1e-12)
 check('exclusion accounting '+label,int(out['total'])==n+int(out['excluded_immature'])+int(out['excluded_coverage']))
for r in read(C/'decomposition.csv'):
 check('decomposition identity '+r['metric']+' '+r['dimensions'],abs(float(r['raw_delta'])-float(r['within_delta'])-float(r['composition_delta']))<1e-12)
for r in read(C/'periods.csv'):
 if r['coverage_lower']:check('coverage bounds '+r['period']+' '+r['metric'],0<=float(r['coverage_lower'])<=float(r['coverage_upper'])<=1)
# Human-readable headline values are checked against independent data reconciliation above.
expected={('early_3','D7_completed'):(246,776),('later_3','D7_completed'):(245,901),('early_3','D30_completed'):(167,776),('later_3','D30_completed'):(158,848)}
for r in period:
 key=(r['period'],r['metric'])
 if key in expected:check('strategy headline '+str(key),(int(r['k']),int(r['n']))==expected[key])
check('power headline',next(int(r['n_per_arm']) for r in read(C/'sample_size.csv') if r['baseline']=='0.2' and r['uplift_absolute']=='0.05')==1094)
strategy=(P/'strategy.md').read_text();research=(P/'research.md').read_text()
for heading in ['Диагностика','Альтернативы','Рекомендация','Продуктовая стратегия','Коммуникационная стратегия','План проверки']:
 check('strategy section '+heading,heading in strategy)
for i in range(1,14):check('evidence entry R'+str(i),f'## R{i} —' in research)
for name in re.findall(r'`(?:calculations/)?([\w_]+\.(?:csv|json))(?=[`: ,])',strategy):
 check('referenced calculation '+name,(C/name).exists() or (P/name).exists())
for f in ['strategy.md','research.md','quality.md','reproduce.md','actions.jsonl','tool_calls.tsv']:
 check('deliverable '+f,(P/f).exists() and (P/f).stat().st_size>0)
check('no unreviewed TODO placeholder',not re.search(r'\bTODO\b|\bTBD\b',strategy))
result=dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),status='ok',checks_passed=len(checks),checks=checks,limitations='Проверка арифметики/целостности и структуры не доказывает причинность, качество исходной телеметрии или эффективность рекомендации.')
(C/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
outputs={str(f.relative_to(P)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(C.iterdir()) if f.is_file()}
(P/'calculation_hashes.json').write_text(json.dumps(outputs,ensure_ascii=False,indent=2)+'\n')
with (P/'actions.jsonl').open('a') as f:f.write(json.dumps(dict(timestamp_utc=result['timestamp_utc'],action='python3 case/verify_local.py',status='ok',details=f'{len(checks)} независимых сверок числителей/знаменателей, входов, декомпозиции, ссылок и структуры. Число проверок не является оценкой уверенности стратегии.'),ensure_ascii=False)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False,indent=2))
