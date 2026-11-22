"""Paired event/window definitions and deliberately naive dashboard-like comparisons."""
import csv,json
from pathlib import Path
from collections import defaultdict
from datetime import date,timedelta,datetime,timezone
P=Path(__file__).resolve().parent;C=P/'calculations'
def read(n):
 with (P/'inputs'/n).open(newline='') as f:return list(csv.DictReader(f))
def write(n,rows):
 with (C/n).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
s=read('signups.csv');e=read('events.csv');c=read('coverage.csv');cov={(r['event_date'],r['platform']):r['status'] for r in c};act=defaultdict(lambda:defaultdict(set))
for r in {r['event_id']:r for r in e}.values():act[r['user_id']][r['event_type']].add(r['event_date'])
def dates(u,a,b):
 d=date.fromisoformat(u['signup_date']);return [(d+timedelta(days=i)).isoformat() for i in range(a,b+1)]
def obs(u,a,b):return all(cov.get((d,u['platform']))=='complete' for d in dates(u,a,b))
def hit(u,t,a,b):return bool(set(dates(u,a,b))&act[u['user_id']][t])
rows=[]
for period,weeks in [('early_2',['2026-06-01','2026-06-08']),('later_2',['2026-06-22','2026-06-29'])]:
 for a,b,exact in [(6,8,7),(28,32,30)]:
  pop=[u for u in s if u['cohort_week'] in weeks and obs(u,a,b)]
  for name,x,y in [('exact',exact,exact),('window',a,b)]:
   k=sum(hit(u,'task_completed',x,y) for u in pop)
   rows.append(dict(period=period,eligibility_window=f'D{a}_{b}',metric=name,n=len(pop),k=k,rate=k/len(pop)))
write('paired_window_sensitivity.csv',rows)
naive=[]
for w in sorted({u['cohort_week'] for u in s}):
 pop=[u for u in s if u['cohort_week']==w]
 for day in [7,30]:
  for t in ['task_completed','app_open','background_sync']:
   k=sum(hit(u,t,day,day) for u in pop);naive.append(dict(cohort_week=w,day=day,event=t,n=len(pop),k=k,rate=k/len(pop),warning='NAIVE: includes immature and incomplete observations as zero'))
write('naive_diagnostic.csv',naive)
with (P/'actions.jsonl').open('a') as f:f.write(json.dumps(dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),action='python3 case/sensitivity.py',status='ok',details='Парные окна на одинаковых пользователях и иллюстрация ошибочного знаменателя; историческая формула дашборда не восстанавливается.'),ensure_ascii=False)+'\n')
print(json.dumps(rows,indent=2));print('LATEST NAIVE',json.dumps(naive[-6:],indent=2))
