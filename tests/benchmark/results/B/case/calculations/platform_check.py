import csv,collections,datetime,pathlib
P=pathlib.Path(__file__).resolve().parent
S=list(csv.DictReader(open(P.parent/'inputs/signups.csv')));A={r['user_id']:r for r in csv.DictReader(open(P/'activation_users.csv'))}
E=collections.defaultdict(lambda:collections.defaultdict(set))
for r in csv.DictReader(open(P.parent/'inputs/events.csv')):E[r['user_id']][r['event_date']].add(r['event_type'])
periods={'early_June':['2026-06-01','2026-06-08'],'late_mature':['2026-06-29','2026-07-06'],'latest_D7':['2026-07-20','2026-07-27']}
rows=[]
for period,cws in periods.items():
 for platform in ('android','ios'):
  us=[u for u in S if u['cohort_week'] in cws and u['platform']==platform]
  for d in (7,30):
   if period=='latest_D7' and d==30:continue
   for definition,types in [('complete',{'task_completed'}),('core',{'task_created','task_completed'}),('open',{'app_open'}),('any',None)]:
    k=0
    for u in us:
     day=str(datetime.date.fromisoformat(u['signup_date'])+datetime.timedelta(days=d));ev=E[u['user_id']].get(day,set());k+=bool(ev if types is None else ev&types)
    rows.append(dict(period=period,platform=platform,metric=f'D{d}_{definition}',k=k,n=len(us),pct=100*k/len(us)))
  for definition in ('created','completed','core','reminder'):
   ar=[A[u['user_id']] for u in us if u['user_id'] in A];k=sum(int(r[definition]) for r in ar)
   rows.append(dict(period=period,platform=platform,metric='early_'+definition,k=k,n=len(ar),pct=100*k/len(ar)))
with (P/'platform_check.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
for r in rows:
 if r['period']!='late_mature':print(r)
