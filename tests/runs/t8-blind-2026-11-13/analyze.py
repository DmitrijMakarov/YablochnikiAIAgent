"""Run from project root: python3 cases/retention-demo/analyze.py. Stdlib only."""
from pathlib import Path
import csv,json,hashlib,collections,datetime,sys
P=Path(__file__).resolve().parent
D=datetime.date.fromisoformat
read=lambda n:list(csv.DictReader((P/'inputs'/n).open()))
users=read('signups.csv'); raw=read('events.csv'); coverage=read('coverage.csv')
U={u['user_id']:u for u in users}; seen={}; conflicts=[]
for e in raw:
 if e['event_id'] in seen and e!=seen[e['event_id']]: conflicts.append(e['event_id'])
 seen[e['event_id']]=e
E=list(seen.values()); cov={(r['event_date'],r['platform']):r['status'] for r in coverage}
by=collections.defaultdict(list); orphans=[]; before=[]
for e in E:
 if e['user_id'] not in U: orphans.append(e); continue
 u=U[e['user_id']]; age=(D(e['event_date'])-D(u['signup_date'])).days
 if age<0: before.append(e); continue
 by[e['user_id']].append((age,e['event_type']))
for u in users:
 s=D(u['signup_date']); u['events']=by[u['user_id']]
 u['activation_create']=any(0<=a<=1 and t=='task_created' for a,t in u['events'])
 u['activation_value']=any(0<=a<=1 and t in ('task_created','task_completed') for a,t in u['events'])
 u['reminder_d1']=any(0<=a<=1 and t=='reminder_enabled' for a,t in u['events'])
 u['activation_complete']=all(cov.get(((s+datetime.timedelta(days=a)).isoformat(),u['platform']))=='complete' for a in [0,1])

def eligible(u,lo,hi):
 s=D(u['signup_date'])
 return all(cov.get(((s+datetime.timedelta(days=a)).isoformat(),u['platform']))=='complete' for a in range(lo,hi+1))
ALL_TYPES=set(e['event_type'] for e in E)
def hit(u,lo,hi,kind):
 types={'value':{'task_created','task_completed'},'completion':{'task_completed'},'foreground':{'app_open','task_created','task_completed','reminder_opened'},'any':ALL_TYPES}[kind]
 return any(lo<=a<=hi and t in types for a,t in u['events'])
def metric(us,lo,hi,kind='value'):
 ok=[u for u in us if eligible(u,lo,hi)]; k=sum(hit(u,lo,hi,kind) for u in ok)
 return {'k':k,'n':len(ok),'excluded':len(us)-len(ok),'pct':round(100*k/len(ok),3) if ok else None}
cohorts=sorted(set(u['cohort_week'] for u in users))
result={'python':sys.version,'hashes':{n:hashlib.sha256((P/'inputs'/n).read_bytes()).hexdigest() for n in ['signups.csv','events.csv','coverage.csv']},'qa':{'users':len(users),'unique_users':len(U),'raw_events':len(raw),'unique_events':len(E),'duplicate_messages':len(raw)-len(E),'conflicting_ids':len(conflicts),'orphans':len(orphans),'pre_signup':len(before),'missing':{f:sum(not u[f] for u in users) for f in ['user_id','signup_date','cohort_week','platform','channel','stated_goal','legacy_setup_flag']},'event_types':dict(collections.Counter(e['event_type'] for e in E)),'partial_coverage':[r for r in coverage if r['status']!='complete']},'cohorts':{},'segments':{},'activation':{},'reminders':{}}
for c in cohorts:
 us=[u for u in users if u['cohort_week']==c]
 result['cohorts'][c]={'size':len(us),'channels':dict(collections.Counter(u['channel'] for u in us))}
 for name,lo,hi in [('D7',7,7),('D30',30,30),('W7',7,13),('W30',28,34)]:
  result['cohorts'][c][name]={k:metric(us,lo,hi,k) for k in ['value','completion','foreground','any']}
 for field in ['channel','platform','stated_goal']:
  for v in sorted(set(u[field] for u in users)):
   vs=[u for u in us if u[field]==v]
   result['segments'][f'{c}/{field}/{v}']={name:metric(vs,lo,hi) for name,lo,hi in [('D7',7,7),('D30',30,30),('W7',7,13),('W30',28,34)]}
 for field in ['activation_create','activation_value','legacy_setup_flag']:
  for v in sorted(set(u[field] for u in users),key=str):
   vs=[u for u in us if u[field]==v and u['activation_complete']]
   result['activation'][f'{c}/{field}/{v}']={'size':len(vs),'D7':metric(vs,7,7),'D30':metric(vs,30,30)}
 for v in [False,True]:
  vs=[u for u in us if u['reminder_d1']==v and u['activation_complete']]
  result['reminders'][f'{c}/{v}']={'size':len(vs),'D7':metric(vs,7,7),'D30':metric(vs,30,30)}
# All-cohort comparison only when every user has complete exact-day coverage.
for name,lo,hi in [('D7',7,7),('D30',30,30),('W7',7,13),('W30',28,34)]:
 full=[c for c in cohorts if all(eligible(u,lo,hi) for u in users if u['cohort_week']==c)]
 result.setdefault('full_cohorts',{})[name]=full
 if full:
  base=[u for u in users if u['cohort_week']==full[0]]
  weights={ch:sum(u['channel']==ch for u in base)/len(base) for ch in sorted(set(u['channel'] for u in users))}
  result.setdefault('standardized',{})[name]={'weights':weights,'rates':{c:round(sum(w*metric([u for u in users if u['cohort_week']==c and u['channel']==ch],lo,hi)['pct'] for ch,w in weights.items()),3) for c in full}}
# Structural consistency and independent brute-force check of first cohort D7.
parts=[]
for i in range(1,6): parts+=read(f'events-part-{i}.csv')
assert parts==raw
assert len(users)==len(U) and not conflicts
first=[u for u in users if u['cohort_week']==cohorts[0]]
ids={e['user_id'] for e in raw if e['user_id'] in U and e['event_type'] in ['task_created','task_completed'] and (D(e['event_date'])-D(U[e['user_id']]['signup_date'])).days==7}
assert sum(u['user_id'] in ids for u in first)==metric(first,7,7)['k']
result['qa']['independent_D7_check']=metric(first,7,7)
result['qa']['cohort_mismatch']=sum((D(u['signup_date'])-datetime.timedelta(days=D(u['signup_date']).weekday())).isoformat()!=u['cohort_week'] for u in users)
result['qa']['create_vs_value_d1_disagreement']=sum(u['activation_create']!=u['activation_value'] for u in users)
(P/'analysis-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'qa':result['qa'],'full_cohorts':result['full_cohorts'],'standardized':result.get('standardized'),'cohorts':{c:{'size':v['size'],'channels':v['channels'],**{m:v[m]['value'] for m in ['D7','D30','W7','W30']}} for c,v in result['cohorts'].items()}},ensure_ascii=False,indent=2))
