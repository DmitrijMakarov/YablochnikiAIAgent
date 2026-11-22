#!/usr/bin/env python3
"""Stdlib-only deterministic analysis of the approved synthetic exports."""
import csv, json, math, hashlib, platform, sys, time
from pathlib import Path
from datetime import date, timedelta, datetime, timezone
from collections import Counter, defaultdict
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'calculations'; OUT.mkdir(exist_ok=True)
started=datetime.now(timezone.utc).isoformat(); tic=time.monotonic()
def read(name):
    with (ROOT/'inputs'/name).open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def write(name,rows):
    if not rows:return
    with (OUT/name).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
signups=read('signups.csv'); events=read('events.csv'); coverage=read('coverage.csv')
users={r['user_id']:r for r in signups}; cov={(date.fromisoformat(r['event_date']),r['platform']):r['status'] for r in coverage}
assert len(users)==len(signups)
assert len(cov)==len(coverage)
assert all(r['data_label']=='SYNTHETIC TEST DATA' for r in signups+events+coverage)
unique={}; conflict=[]
for i,r in enumerate(events,2):
    if r['event_id'] in unique and unique[r['event_id']][0]!=r:conflict.append(i)
    unique.setdefault(r['event_id'],(r,i))
assert not conflict
orphan=[]; before=[]; acts=defaultdict(lambda:defaultdict(set)); loc=defaultdict(list)
for r,i in unique.values():
    u=users.get(r['user_id'])
    if u is None:orphan.append(i);continue
    age=(date.fromisoformat(r['event_date'])-date.fromisoformat(u['signup_date'])).days
    if age<0:before.append(i);continue
    acts[r['user_id']][r['event_type']].add(age)
    loc[r['user_id']].append(i)
assert not orphan and not before
weeks=sorted({u['cohort_week'] for u in signups}); end=max(d for d,p in cov)
for u in signups:
    d=date.fromisoformat(u['signup_date']); assert date.fromisoformat(u['cohort_week'])==d-timedelta(days=d.weekday())
    u['signup']=d

def eligible(u,a,b):
    return all(cov.get((u['signup']+timedelta(days=i),u['platform']))=='complete' for i in range(a,b+1))
def mature(u,b):return u['signup']+timedelta(days=b)<=end
def hit(u,event,a,b):
    types=event.split('|')
    return any(a<=day<=b for t in types for day in acts[u['user_id']][t])
def wilson(k,n):
    if not n:return (None,None)
    z=1.959963984540054;p=k/n; den=1+z*z/n
    c=(p+z*z/(2*n))/den;rad=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return c-rad,c+rad

def summary(pop,event,a,b):
    maturepop=[u for u in pop if mature(u,b)];obs=[u for u in pop if eligible(u,a,b)]
    k=sum(hit(u,event,a,b) for u in obs);n=len(obs);lo,hi=wilson(k,n)
    # Bounds for time-mature accounts with incomplete coverage, assuming no false positive events.
    known_hits=sum(hit(u,event,a,b) for u in maturepop)
    unresolved=sum(not eligible(u,a,b) and not hit(u,event,a,b) for u in maturepop)
    return dict(total=len(pop),time_mature=len(maturepop),excluded_immature=len(pop)-len(maturepop),excluded_coverage=len(maturepop)-n,n=n,k=k,rate=k/n if n else None,ci_low=lo,ci_high=hi,coverage_lower=known_hits/len(maturepop) if maturepop else None,coverage_upper=(known_hits+unresolved)/len(maturepop) if maturepop else None)
metrics=[('D7_completed','task_completed',7,7),('D30_completed','task_completed',30,30),('D7_open','app_open',7,7),('D30_open','app_open',30,30),('D6_8_completed','task_completed',6,8),('D28_32_completed','task_completed',28,32),('D1_7_completed','task_completed',1,7),('D24_30_completed','task_completed',24,30),('D7_any_foreground','app_open|task_created|task_completed|reminder_enabled|reminder_opened',7,7),('D30_any_foreground','app_open|task_created|task_completed|reminder_enabled|reminder_opened',30,30)]
coh=[]
for w in weeks:
    pop=[u for u in signups if u['cohort_week']==w]
    for name,ev,a,b in metrics:
        whole_week_mature=date.fromisoformat(w)+timedelta(days=6+b)<=end
        coh.append(dict(cohort_week=w,metric=name,whole_week_mature=whole_week_mature,**summary(pop,ev,a,b)))
write('cohorts.csv',coh)
periods={'early_3':weeks[:3],'later_3':weeks[3:6],'recent_3':weeks[6:9],'all_common_6':weeks[:6],'all_D7_9':weeks[:9]}
periodrows=[]
for period,ws in periods.items():
    pop=[u for u in signups if u['cohort_week'] in ws]
    for name,ev,a,b in metrics:
        periodrows.append(dict(period=period,metric=name,**summary(pop,ev,a,b)))
write('periods.csv',periodrows)
segrows=[]
for period,ws in periods.items():
    pop=[u for u in signups if u['cohort_week'] in ws]
    for dim in ['platform','channel','stated_goal','legacy_setup_flag']:
        for value in sorted({u[dim] for u in signups}):
            sub=[u for u in pop if u[dim]==value]
            for name,ev,a,b in metrics[:4]:segrows.append(dict(period=period,dimension=dim,value=value or '(missing)',metric=name,**summary(sub,ev,a,b)))
write('segments.csv',segrows)
# Sequential exact decomposition: raw delta = early-weight within delta + composition at later rates.
decomp=[]; cells=[]
for name,ev,a,b in metrics[:2]:
 for dims in [('channel',),('platform',),('channel','platform'),('channel','platform','stated_goal')]:
    pops=[[u for u in signups if u['cohort_week'] in periods[p] and eligible(u,a,b)] for p in ['early_3','later_3']]
    keys=sorted({tuple(u[d] for d in dims) for pop in pops for u in pop})
    vals=[]
    for key in keys:
        counts=[]
        for pop in pops:
            sub=[u for u in pop if tuple(u[d] for d in dims)==key]
            counts.append((len(sub),sum(hit(u,ev,a,b) for u in sub)))
        assert all(n>0 for n,k in counts),('no overlap',key)
        (n0,k0),(n1,k1)=counts;p0=k0/n0;p1=k1/n1;w0=n0/len(pops[0]);w1=n1/len(pops[1])
        vals.append((w0,w1,p0,p1,n0,n1))
        cells.append(dict(metric=name,dimensions='+'.join(dims),cell='|'.join(key),n_early=n0,k_early=k0,rate_early=p0,n_later=n1,k_later=k1,rate_later=p1,weight_early=w0,weight_later=w1))
    raw0=sum(w0*p0 for w0,w1,p0,p1,n0,n1 in vals);raw1=sum(w1*p1 for w0,w1,p0,p1,n0,n1 in vals)
    std1=sum(w0*p1 for w0,w1,p0,p1,n0,n1 in vals)
    within=sum(w0*(p1-p0) for w0,w1,p0,p1,n0,n1 in vals)
    composition=sum((w1-w0)*p1 for w0,w1,p0,p1,n0,n1 in vals)
    variance=sum(w0*w0*(p0*(1-p0)/n0+p1*(1-p1)/n1) for w0,w1,p0,p1,n0,n1 in vals)
    assert abs(raw1-raw0-within-composition)<1e-10
    decomp.append(dict(metric=name,dimensions='+'.join(dims),early_raw=raw0,later_raw=raw1,later_standardized=std1,raw_delta=raw1-raw0,within_delta=within,within_ci_low=within-1.96*math.sqrt(variance),within_ci_high=within+1.96*math.sqrt(variance),composition_delta=composition,min_cell_n=min(min(v[4:]) for v in vals)))
write('decomposition.csv',decomp);write('standardization_cells.csv',cells)
# Baseline behaviors all observable on D0-D2, no outcome leakage into D7/D30.
features={
'created_D0_2':lambda u:hit(u,'task_created',0,2),
'completed_D0_2':lambda u:hit(u,'task_completed',0,2),
'created_or_completed_D0_2':lambda u:hit(u,'task_created|task_completed',0,2),
'completed_no_created_D0_2':lambda u:hit(u,'task_completed',0,2) and not hit(u,'task_created',0,2),
'reminder_enabled_D0_2':lambda u:hit(u,'reminder_enabled',0,2),
'reminder_opened_D0_2':lambda u:hit(u,'reminder_opened',0,2)}
beh=[]
for period,ws in periods.items():
    pop=[u for u in signups if u['cohort_week'] in ws and eligible(u,0,2)]
    for fname,fn in features.items():
        for value in [False,True]:
            sub=[u for u in pop if fn(u)==value]
            for name,ev,a,b in metrics[:2]:beh.append(dict(period=period,feature=fname,value=value,metric=name,**summary(sub,ev,a,b)))
write('early_behaviors.csv',beh)
# Day-level outcome labels with source row locators for direct inspection, no external transmission.
userrows=[]
for i,u in enumerate(signups,2):
    row={k:v for k,v in u.items() if k not in ['data_label','signup']}
    row['signup_csv_line']=i
    for fname,fn in features.items():row[fname]=int(fn(u)) if eligible(u,0,2) else ''
    for name,ev,a,b in metrics:
        row[name+'_eligible']=eligible(u,a,b);row[name+'_hit']=int(hit(u,ev,a,b)) if eligible(u,a,b) else ''
    userrows.append(row)
write('user_metrics.csv',userrows)
# Sensitivity: common fully observed entire cohorts rather than individual exclusions.
clean=[]
for name,ev,a,b in metrics[:2]:
    cleanweeks=[w for w in weeks[:6] if all(eligible(u,a,b) for u in signups if u['cohort_week']==w)]
    for per in ['early_3','later_3']:
        pop=[u for u in signups if u['cohort_week'] in periods[per] and u['cohort_week'] in cleanweeks]
        clean.append(dict(metric=name,period=per,kept_weeks='|'.join(w for w in periods[per] if w in cleanweeks),**summary(pop,ev,a,b)))
write('whole_cohort_sensitivity.csv',clean)
# Prospective sample size, two-sided 5%, 80% power, independent equal arms, normal approximation.
power=[]
for baseline in [0.15,0.20,0.25,0.30]:
 for uplift in [0.02,0.03,0.05]:
    p1=baseline+uplift;bar=(baseline+p1)/2
    n=math.ceil(((1.95996398454*math.sqrt(2*bar*(1-bar))+0.84162123357*math.sqrt(baseline*(1-baseline)+p1*(1-p1)))**2)/(uplift**2))
    power.append(dict(baseline=baseline,uplift_absolute=uplift,n_per_arm=n,total_two_arms=2*n,weeks_at_300_signups=2*n/300,weeks_at_300_with_50pct_eligible=2*n/150))
write('sample_size.csv',power)
qc=dict(signups=len(signups),unique_users=len(users),raw_events=len(events),deduplicated_events=len(unique),duplicate_extra_rows=len(events)-len(unique),conflicting_ids=len(conflict),orphan_events=len(orphan),pre_signup_events=len(before),coverage_rows=len(coverage),coverage_start=str(min(d for d,p in cov)),coverage_end=str(end),partial=[r for r in coverage if r['status']!='complete'],signup_missing={k:sum(not u[k] for u in signups) for k in ['channel','stated_goal','legacy_setup_flag']},event_type_unique=dict(Counter(r['event_type'] for r,i in unique.values())),python=sys.version,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(OUT/'qc.json').write_text(json.dumps(qc,ensure_ascii=False,indent=2)+'\n')
with (ROOT/'actions.jsonl').open('a') as f:f.write(json.dumps(dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),started_utc=started,seconds=time.monotonic()-tic,action='python3 case/analyze.py',status='ok',details='Проверки структуры, дедупликация, eligibility, когорты и периоды, сегменты, стандартизация, ранние действия, чувствительность, мощность; расчёты сохранены локально.'),ensure_ascii=False)+'\n')
print(json.dumps(qc,ensure_ascii=False,indent=2))
print('\nPRIMARY PERIODS')
for r in periodrows:
    if r['metric'] in ['D7_completed','D30_completed','D7_open','D30_open','D6_8_completed','D28_32_completed']: print(r)
print('\nDECOMPOSITION')
for r in decomp:print(r)
