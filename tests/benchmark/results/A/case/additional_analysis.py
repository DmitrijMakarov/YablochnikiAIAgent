"""Additional checks supporting the strategy, stdlib only."""
import csv,json,math
from pathlib import Path
from datetime import datetime,timezone
P=Path(__file__).resolve().parent;C=P/'calculations'
def read(n):return list(csv.DictReader(open(C/n)))
def write(n,rows):
 with (C/n).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
period=read('periods.csv');dif=[]
for metric in sorted({r['metric'] for r in period}):
 e=next(r for r in period if r['period']=='early_3' and r['metric']==metric);l=next(r for r in period if r['period']=='later_3' and r['metric']==metric)
 p0=float(e['rate']);p1=float(l['rate']);n0=int(e['n']);n1=int(l['n']);se=math.sqrt(p0*(1-p0)/n0+p1*(1-p1)/n1)
 dif.append(dict(metric=metric,delta=p1-p0,ci_low=p1-p0-1.96*se,ci_high=p1-p0+1.96*se,relative_delta=p1/p0-1))
write('period_differences.csv',dif)
u=read('user_metrics.csv');out=[]
for per,ws in [('early_3',['2026-06-01','2026-06-08','2026-06-15']),('later_3',['2026-06-22','2026-06-29','2026-07-06']),('all_common_6',['2026-06-01','2026-06-08','2026-06-15','2026-06-22','2026-06-29','2026-07-06'])]:
 pop=[r for r in u if r['cohort_week'] in ws]
 for feat in ['created_D0_2','completed_D0_2','created_or_completed_D0_2','completed_no_created_D0_2','reminder_enabled_D0_2']:
  for dim in ['all','legacy_setup_flag','channel','stated_goal']:
   values=['all'] if dim=='all' else sorted({r[dim] for r in pop})
   for val in values:
    sub=[r for r in pop if dim=='all' or r[dim]==val];obs=[r for r in sub if r[feat]!='']
    out.append(dict(period=per,feature=feat,dimension=dim,value=val or '(missing)',n=len(obs),k=sum(int(r[feat]) for r in obs),rate=sum(int(r[feat]) for r in obs)/len(obs)))
write('activation_rates.csv',out)
# Same users/whole mature weeks for wider-window sensitivity: avoid comparing partly mature July 6 cohort.
with (P/'inputs'/'events.csv').open() as f:events=list(csv.DictReader(f))
with (P/'inputs'/'coverage.csv').open() as f:coverage=list(csv.DictReader(f))
from datetime import date,timedelta
cov={(r['event_date'],r['platform']):r['status'] for r in coverage}; acts={}
for r in events:
 if r['event_type']=='task_completed':acts.setdefault(r['user_id'],set()).add(r['event_date'])
rows=[]
for per,ws in [('early_2',['2026-06-01','2026-06-08']),('later_2',['2026-06-22','2026-06-29'])]:
 for a,b in [(30,30),(28,32),(24,30),(7,7),(6,8)]:
  pop=[r for r in u if r['cohort_week'] in ws];obs=[]
  for r in pop:
   d=date.fromisoformat(r['signup_date']);dates=[(d+timedelta(days=i)).isoformat() for i in range(a,b+1)]
   if all(cov.get((day,r['platform']))=='complete' for day in dates):obs.append((r,dates))
  k=sum(bool(set(ds)&acts.get(r['user_id'],set())) for r,ds in obs)
  rows.append(dict(period=per,window=f'D{a}_{b}',total=len(pop),n=len(obs),k=k,rate=k/len(obs)))
write('window_mature_sensitivity.csv',rows)
with (P/'actions.jsonl').open('a') as f:f.write(json.dumps(dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),action='python3 case/additional_analysis.py',status='ok',details='Интервалы разностей, ранние действия и legacy, окна возврата на целых зрелых неделях.'),ensure_ascii=False)+'\n')
print('DIFFERENCES',json.dumps(dif,indent=2));print('ACTIVATION ALL',json.dumps([r for r in out if r['dimension']=='all'],indent=2));print('WINDOWS',json.dumps(rows,indent=2))
