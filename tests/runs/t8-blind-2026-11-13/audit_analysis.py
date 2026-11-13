"""Independent checks using raw row sets, without importing the analysis code."""
import csv,json,hashlib,datetime,math
from pathlib import Path
P=Path(__file__).resolve().parent
rows=lambda n:list(csv.DictReader((P/'inputs'/n).open()))
U=rows('signups.csv'); E=rows('events.csv'); C=rows('coverage.csv'); result=json.loads((P/'analysis-results.json').read_text()); D=datetime.date.fromisoformat
cov={(r['platform'],D(r['event_date'])) for r in C if r['status']=='complete'}
idx={u['user_id']:u for u in U}; hits={}; complete=lambda u,days:all((u['platform'],D(u['signup_date'])+datetime.timedelta(days=a)) in cov for a in days)
for e in E:
 u=idx[e['user_id']]; a=(D(e['event_date'])-D(u['signup_date'])).days
 hits.setdefault((e['event_type'],a),set()).add(e['user_id'])
checks=[]
for cohort, values in result['cohorts'].items():
 us=[u for u in U if u['cohort_week']==cohort]
 for name,lo,hi in [('D7',7,7),('D30',30,30),('W7',7,13),('W30',28,34)]:
  eligible={u['user_id'] for u in us if complete(u,range(lo,hi+1))}; active=set()
  for a in range(lo,hi+1):active|=hits.get(('task_created',a),set())|hits.get(('task_completed',a),set())
  expected=values[name]['value']; got={'k':len(active&eligible),'n':len(eligible)}
  assert got['k']==expected['k'] and got['n']==expected['n'],(cohort,name,got,expected)
  checks.append({'cohort':cohort,'metric':name,**got})
# Deduplication does not affect distinct-user-day rates, checked against raw rows above.
unique={}
for e in E:
 key=e['event_id']
 assert key not in unique or unique[key]==e
 unique[key]=e
assert len(E)-len(unique)==1342
assert len(idx)==3020
assert sum(not u['channel'] for u in U)==155
assert sum(not u['stated_goal'] for u in U)==404
assert sum(not u['legacy_setup_flag'] for u in U)==246
activation={u['user_id'] for u in U if any(u['user_id'] in hits.get((t,a),set()) for t in ['task_created','task_completed'] for a in [0,1])}
create={u['user_id'] for u in U if any(u['user_id'] in hits.get(('task_created',a),set()) for a in [0,1])}
assert len(activation-create)==208
associations={}
for name,days in [('D7',[7]),('D30',[30])]:
 eligible=[u for u in U if u['cohort_week'] in result['full_cohorts'][name] and complete(u,[0,1])]
 ret=set().union(*(hits.get((t,a),set()) for t in ['task_created','task_completed'] for a in days))
 for typ,members in [('value',activation),('reminder',hits.get(('reminder_enabled',0),set())|hits.get(('reminder_enabled',1),set()))]:
  for flag in [False,True]:
   ids={u['user_id'] for u in eligible if (u['user_id'] in members)==flag}
   associations[f'{name}/{typ}/{flag}']={'k':len(ids&ret),'n':len(ids)}
assert associations['D7/value/True']=={'k':572,'n':1661}
assert associations['D7/value/False']=={'k':123,'n':598}
assert associations['D7/reminder/True']=={'k':275,'n':661}
assert associations['D7/reminder/False']=={'k':420,'n':1598}
assert associations['D30/reminder/True']=={'k':113,'n':412}
assert associations['D30/reminder/False']=={'k':182,'n':970}
# Direct standardization independently, using exact unrounded strata proportions.
weights={ch:sum(u['cohort_week']=='2026-06-01' and u['channel']==ch for u in U)/242 for ch in ['', 'organic','paid_social','referral']}
standard={}
ret=hits.get(('task_created',7),set())|hits.get(('task_completed',7),set())
for c in ['2026-06-01','2026-07-27']:
 total=0
 for ch,w in weights.items():
  ids={u['user_id'] for u in U if u['cohort_week']==c and u['channel']==ch}
  total+=w*len(ids&ret)/len(ids)
 standard[c]=100*total
 assert abs(100*total-result['standardized']['D7']['rates'][c])<.001
# Manual row example: u00001 registered 2026-06-02, target D7 2026-06-09.
u=idx['u00001']; example=[e for e in E if e['user_id']=='u00001' and e['event_date']=='2026-06-09']
checks_out={'status':'passed','independent_cells':len(checks),'cells':checks,'associations':associations,'standardized_D7':standard,'manual_account':{'signup':u,'target_D7':'2026-06-09','events':example},'original_events_sha256':hashlib.sha256((P/'inputs/events.csv').read_bytes()).hexdigest()}
(P/'audit-checks.json').write_text(json.dumps(checks_out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in checks_out.items() if k not in ['cells','manual_account']},indent=2))
