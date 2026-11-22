"""Exploratory D30 associations among D0-3 activation strata, no causal interpretation."""
import csv,pathlib,datetime
P=pathlib.Path(__file__).resolve().parent
u={r['user_id']:r for r in csv.DictReader(open(P.parent/'inputs/signups.csv'))}
a=list(csv.DictReader(open(P/'activation_users.csv')));e={}
for r in csv.DictReader(open(P.parent/'inputs/events.csv')):
 if r['event_type']=='task_completed':e.setdefault(r['user_id'],set()).add(r['event_date'])
rows=[]
for restrict in ('all','core_activated'):
 for field in ('goal','channel'):
  for val in sorted({r[field] for r in a}):
   for reminder in ('0','1'):
    v=[r for r in a if r['cohort'] in ('2026-06-29','2026-07-06') and r[field]==val and r['reminder']==reminder and (restrict=='all' or r['core']=='1')]
    k=sum(str(datetime.date.fromisoformat(u[r['user_id']]['signup_date'])+datetime.timedelta(days=30)) in e.get(r['user_id'],set()) for r in v)
    rows.append(dict(restriction=restrict,dimension=field,segment=val,reminder=reminder,n=len(v),k=k,pct=100*k/len(v) if v else None))
with (P/'reminder_strata.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print('Saved reminder_strata.csv, rows:',len(rows))
