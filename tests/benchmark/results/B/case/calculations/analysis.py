"""Stdlib-only deterministic analysis. Never writes inputs or supplied tools."""
import csv,json,hashlib,collections,math,datetime,pathlib
P=pathlib.Path(__file__).resolve().parent; ROOT=P.parent; IN=ROOT/'inputs'
D=datetime.date.fromisoformat

def load(n):
 with (IN/n).open(newline='') as f:return list(csv.DictReader(f))
def save(n,rows):
 if not rows:return
 with (P/n).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def pct(k,n):return 100*k/n if n else None
def wilson(k,n):
 if not n:return [None,None]
 z=1.959963984540054;p=k/n;a=1+z*z/n;b=(p+z*z/(2*n))/a;c=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/a
 return [100*(b-c),100*(b+c)]
S=load('signups.csv');E=load('events.csv');C=load('coverage.csv');U={r['user_id']:r for r in S}
coverage={(D(r['event_date']),r['platform']):r['status'] for r in C};cut=max(D(r['event_date']) for r in C)
quality={'signups':len(S),'events_raw':len(E),'signup_duplicate_ids':len(S)-len(U),'cutoff':str(cut),'coverage_rows':len(C),'coverage_duplicate_keys':len(C)-len(coverage),'coverage_partial':[r for r in C if r['status']!='complete'],'missing':{k:sum(not r[k] for r in S) for k in S[0]},'ranges':{n:[2,len(v)+1] for n,v in [('signups.csv',S),('events.csv',E),('coverage.csv',C)]}}
seen={};events=collections.defaultdict(lambda:collections.defaultdict(set));unknown=[];conflicts=[];before=[]
for line,r in enumerate(E,2):
 eid=r['event_id']
 if eid in seen:
  if seen[eid]!=r:conflicts.append(line)
  continue
 seen[eid]=r
 if r['user_id'] not in U:unknown.append(line);continue
 u=U[r['user_id']];day=(D(r['event_date'])-D(u['signup_date'])).days
 if day<0:before.append(line);continue
 events[r['user_id']][r['event_type']].add(day)
quality.update(events_unique=len(seen),duplicate_messages=len(E)-len(seen),conflicting_duplicate_lines=conflicts,unknown_user_lines=unknown,pre_signup_lines=before,event_types=dict(collections.Counter(r['event_type'] for r in seen.values())))
# Preserve every source record with original physical line. Chunks under CLI record cap.
for start in range(0,len(E),19000):
 with (P/f'events_rows_{start+2:06d}_{min(start+19000,len(E))+1:06d}.jsonl').open('w') as out:
  for i,r in enumerate(E[start:start+19000],start+2):out.write(json.dumps({'source':'S-003@1','locator':f'line:{i}','row':r},ensure_ascii=False)+'\n')
cohorts=sorted({r['cohort_week'] for r in S})
# Fully observed exact metric uses target day only; interval uses every day in interval.
metrics={'D7_complete':(7,7,{'task_completed'}),'D30_complete':(30,30,{'task_completed'}),'D7_core':(7,7,{'task_created','task_completed'}),'D30_core':(30,30,{'task_created','task_completed'}),'D7_open':(7,7,{'app_open'}),'D30_open':(30,30,{'app_open'}),'D7_any':(7,7,None),'D30_any':(30,30,None),'W7_complete':(7,13,{'task_completed'}),'W30_complete':(28,34,{'task_completed'})}
def observed(u,a,b):
 days=[D(u['signup_date'])+datetime.timedelta(days=i) for i in range(a,b+1)]
 if days[-1]>cut:return 'immature'
 if not u['platform']:return 'unknown_platform'
 if any(coverage.get((t,u['platform']))!='complete' for t in days):return 'incomplete'
 return 'observed'
def hit(u,a,b,types):
 return any(a<=i<=b for t,days in events[u['user_id']].items() if types is None or t in types for i in days)
def stat(users,metric):
 a,b,types=metrics[metric];bal=collections.Counter(observed(u,a,b) for u in users)
 good=[u for u in users if observed(u,a,b)=='observed'];k=sum(hit(u,a,b,types) for u in good);n=len(good)
 # calendar-mature but incomplete, pessimistic/optimistic whole-mature bounds
 mature=[u for u in users if observed(u,a,b)!='immature'];obs_incomplete=[u for u in mature if observed(u,a,b)!='observed']
 knownpos=sum(hit(u,a,b,types) for u in obs_incomplete)
 naive=sum(hit(u,a,b,types) for u in users)
 return dict(total=len(users),immature=bal['immature'],unknown_platform=bal['unknown_platform'],incomplete=bal['incomplete'],n=n,k=k,pct=pct(k,n),lo95=wilson(k,n)[0],hi95=wilson(k,n)[1],naive_k=naive,naive_pct=pct(naive,len(users)),mature_n=len(mature),mature_lower_pct=pct(k+knownpos,len(mature)),mature_upper_pct=pct(k+len(obs_incomplete),len(mature)))
weekly=[]
for cw in cohorts:
 for m in metrics:weekly.append(dict(cohort=cw,metric=m,**stat([u for u in S if u['cohort_week']==cw],m)))
save('weekly.csv',weekly)
# Predeclared calendar comparisons: June first/last week for endpoints, June early/late halves;
# July 6 vs June29 as latest completely mature D30 cohort, and June29-Jul6 vs June15-22.
periods={'June_first':['2026-06-01'],'June_last':['2026-06-22'],'early_June':['2026-06-01','2026-06-08'],'late_June':['2026-06-15','2026-06-22'],'June29':['2026-06-29'],'July6':['2026-07-06'],'late_mature':['2026-06-29','2026-07-06'],'latest_D7':['2026-07-20','2026-07-27'],'early_all':cohorts[:3],'late_all':cohorts[-3:]}
comparisons=[('early_June','late_mature'),('early_June','latest_D7'),('June_first','July6'),('early_June','late_June'),('late_June','late_mature'),('early_all','late_all')]
periodrows=[];diffs=[];segments=[];decomp=[]
for pn,cws in periods.items():
 for m in metrics:periodrows.append(dict(period=pn,cohorts='|'.join(cws),metric=m,**stat([u for u in S if u['cohort_week'] in cws],m)))
for p0,p1 in comparisons:
 for m in metrics:
  us=[[u for u in S if u['cohort_week'] in periods[p]] for p in (p0,p1)]
  a,b=[stat(v,m) for v in us];se=math.sqrt(sum(x['k']/x['n']*(1-x['k']/x['n'])/x['n'] for x in (a,b))) if a['n'] and b['n'] else None
  d=b['pct']-a['pct'] if se is not None else None
  diffs.append(dict(p0=p0,p1=p1,metric=m,k0=a['k'],n0=a['n'],k1=b['k'],n1=b['n'],delta_pp=d,lo95=d-196*se if se is not None else None,hi95=d+196*se if se is not None else None))
  if m not in ('D7_complete','D30_complete','W7_complete','W30_complete'):continue
  for field in ('channel','platform','stated_goal','channel_platform'):
   def key(u):return (u['channel'] or 'unknown')+'|'+u['platform'] if field=='channel_platform' else u[field] or 'unknown'
   keys=sorted({key(u) for group in us for u in group});parts=[]
   for v in keys:
    stats=[stat([u for u in group if key(u)==v],m) for group in us]
    for p,s,tot in zip((p0,p1),stats,(a,b)):
     segments.append(dict(comparison=p0+'__'+p1,period=p,metric=m,dimension=field,segment=v,weight=s['n']/tot['n'] if tot['n'] else None,**s))
    if all(x['n'] for x in stats) and a['n'] and b['n']:
     w0,w1=stats[0]['n']/a['n'],stats[1]['n']/b['n'];r0,r1=stats[0]['k']/stats[0]['n'],stats[1]['k']/stats[1]['n'];parts.append((w0,w1,r0,r1))
   if len(parts)==len(keys):
    mix=sum((w1-w0)*r0 for w0,w1,r0,r1 in parts);within=sum(w1*(r1-r0) for w0,w1,r0,r1 in parts)
    std0=sum((w0+w1)/2*r0 for w0,w1,r0,r1 in parts);std1=sum((w0+w1)/2*r1 for w0,w1,r0,r1 in parts)
    assert abs(100*(mix+within)-d)<1e-9
    decomp.append(dict(p0=p0,p1=p1,metric=m,dimension=field,mix_pp=100*mix,within_pp=100*within,total_pp=d,std0_pct=100*std0,std1_pct=100*std1,std_delta_pp=100*(std1-std0)))
save('periods.csv',periodrows);save('sensitivity.csv',diffs);save('segments.csv',segments);save('decomposition.csv',decomp)
# Early activation, all users with full D0-3; explicit create, complete and their union.
activation=[];assoc=[];actrows=[]
for u in S:
 obs=observed(u,0,3)
 if obs=='observed':
  cr=hit(u,0,3,{'task_created'});co=hit(u,0,3,{'task_completed'});re=hit(u,0,3,{'reminder_enabled'})
  actrows.append(dict(user_id=u['user_id'],cohort=u['cohort_week'],channel=u['channel'] or 'unknown',platform=u['platform'],goal=u['stated_goal'] or 'unknown',legacy=u['legacy_setup_flag'] or 'unknown',created=int(cr),completed=int(co),core=int(cr or co),reminder=int(re)))
quality['activation_balance']=dict(collections.Counter(observed(u,0,3) for u in S))
for pn,cws in {**periods,'all':cohorts}.items():
 ar=[r for r in actrows if r['cohort'] in cws]
 for field in ('created','completed','core','reminder'):
  k=sum(r[field] for r in ar);activation.append(dict(period=pn,definition=field,k=k,n=len(ar),pct=pct(k,len(ar))))
 for legacy in ('0','1','unknown'):
  for created in (0,1):
   for completed in (0,1):
    k=sum(r['legacy']==legacy and r['created']==created and r['completed']==completed for r in ar)
    activation.append(dict(period=pn,definition=f'legacy={legacy}|created={created}|completed={completed}',k=k,n=len(ar),pct=pct(k,len(ar))))
 for m in ('D7_complete','D30_complete','W30_complete'):
  for f in ('created','completed','core','reminder','legacy'):
   for v in (('0','1','unknown') if f=='legacy' else (0,1)):
    users=[U[r['user_id']] for r in ar if r[f]==v];assoc.append(dict(period=pn,metric=m,activation=f,value=v,**stat(users,m)))
save('activation.csv',activation);save('activation_associations.csv',assoc);save('activation_users.csv',actrows)
# Unknown attributes by week and partial-day affected accounts, including observed upper/lower bounds.
save('missing_by_cohort.csv',[dict(cohort=cw,n=len(g),channel_missing=sum(not u['channel'] for u in g),goal_missing=sum(not u['stated_goal'] for u in g),legacy_missing=sum(not u['legacy_setup_flag'] for u in g)) for cw in cohorts for g in [[u for u in S if u['cohort_week']==cw]]])
quality['same_day_duplicate_user_type_days']=sum(len([r for r in seen.values() if r['user_id'] in U])-sum(len(days) for ue in events.values() for days in ue.values()) for _ in [0])
quality['input_versions']={p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(IN.iterdir()) if p.is_file()}
(P/'quality_data.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(quality,ensure_ascii=False,indent=2))
print('Key D7/D30 comparisons:')
for r in diffs:
 if r['metric'] in ('D7_complete','D30_complete','W30_complete'):print(r)
print('Decomposition channel:')
for r in decomp:
 if r['dimension']=='channel' and r['metric'] in ('D7_complete','D30_complete'):print(r)
