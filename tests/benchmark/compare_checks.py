"""Independent numeric reception; never imports participant code or generator.
Run from any directory: python3 tests/benchmark/compare_checks.py
"""
import csv
import hashlib
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RAW = HERE / 'results'
I = ROOT / 'cases/retention-demo/inputs'

def rows(p):
    with p.open(newline='') as f:
        return list(csv.DictReader(f))

users = rows(I / 'signups.csv')
events = rows(I / 'events.csv')
cov = {(r['event_date'], r['platform']): r['status'] for r in rows(I / 'coverage.csv')}
cut = date.fromisoformat(max(d for d, p in cov))
weeks = sorted({u['cohort_week'] for u in users})
seen = {}
hits = defaultdict(lambda: defaultdict(set))
for r in events:
    if r['event_id'] in seen:
        assert seen[r['event_id']] == r
    seen[r['event_id']] = r
for r in seen.values():
    hits[r['user_id']][r['event_date']].add(r['event_type'])
assert len({u['user_id'] for u in users}) == len(users)

def complete(u, a, b):
    d = date.fromisoformat(u['signup_date'])
    return all(cov.get(((d + timedelta(days=t)).isoformat(), u['platform'])) == 'complete' for t in range(a, b + 1))

def event(u, a, b, types):
    d = date.fromisoformat(u['signup_date'])
    return any((bool(hits[u['user_id']].get((d + timedelta(days=t)).isoformat(), set())) if types is None else
                bool(hits[u['user_id']].get((d + timedelta(days=t)).isoformat(), set()) & types)) for t in range(a, b + 1))

MA = {f'D{day}_{name}': (day, day, types) for day in (7, 30) for name, types in
      [('completed', {'task_completed'}), ('open', {'app_open'}),
       ('any_foreground', {'app_open','task_created','task_completed','reminder_enabled','reminder_opened'})]}
for label, a, b in [('D6_8',6,8), ('D28_32',28,32), ('D1_7',1,7), ('D24_30',24,30)]:
    MA[label+'_completed'] = (a,b,{'task_completed'})
MB = {f'D{day}_{name}': (day,day,types) for day in (7,30) for name, types in
      [('complete',{'task_completed'}),('core',{'task_created','task_completed'}),('open',{'app_open'}),('any',None)]}
MB.update(W7_complete=(7,13,{'task_completed'}), W30_complete=(28,34,{'task_completed'}))
PA = dict(early_3=weeks[:3], later_3=weeks[3:6], recent_3=weeks[6:9], all_common_6=weeks[:6], all_D7_9=weeks[:9])
PB = dict(June_first=weeks[:1], June_last=weeks[3:4], early_June=weeks[:2], late_June=weeks[2:4],
          June29=weeks[4:5], July6=weeks[5:6], late_mature=weeks[4:6], latest_D7=weeks[7:9], early_all=weeks[:3], late_all=weeks[-3:], all=weeks)
features = {'created_D0_2': ({'task_created'},False), 'completed_D0_2': ({'task_completed'},False),
            'created_or_completed_D0_2': ({'task_created','task_completed'},False),
            'completed_no_created_D0_2': ({'task_completed'},True), 'reminder_enabled_D0_2': ({'reminder_enabled'},False),
            'reminder_opened_D0_2': ({'reminder_opened'},False)}
def feature(u, f):
    types, exclude = features[f]
    return event(u,0,2,types) and not (exclude and event(u,0,2,{'task_created'}))

def activation(u, f):
    if f == 'legacy': return u['legacy_setup_flag'] or 'unknown'
    return int(event(u,0,3,{'created':{'task_created'},'completed':{'task_completed'},'core':{'task_created','task_completed'},'reminder':{'reminder_enabled'}}[f]))

# Cache each account's outcome; independent raw CSV reader, no participant tables used as inputs.
cache = {}
for mode, metrics in [('A',MA),('B',MB)]:
    for m,(a,b,types) in metrics.items():
        for u in users:
            mature = date.fromisoformat(u['signup_date']) + timedelta(days=b) <= cut
            cache[mode,m,u['user_id']] = (mature, complete(u,a,b), event(u,a,b,types))

out = {'method':'independent stdlib CSV/set calculation; no participant imports',
       'input_hashes': {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(I.iterdir()) if p.is_file()},
       'qc':{'users':len(users),'raw_events':len(events),'unique_events':len(seen),'extra_duplicates':len(events)-len(seen)},
       'checks':{},'mismatches':[],'main':{},'balance':{},'common_periods':{}}

def check(mode, filename, rownum, row, pop, m):
    vals = [cache[mode,m,u['user_id']] for u in pop]
    n = sum(c for mature,c,hit in vals); k = sum(c and hit for mature,c,hit in vals)
    exp = dict(n=n,k=k,total=len(vals))
    if mode == 'A':
        exp.update(time_mature=sum(t for t,c,h in vals),excluded_immature=sum(not t for t,c,h in vals),excluded_coverage=sum(t and not c for t,c,h in vals))
    else:
        exp.update(immature=sum(not t for t,c,h in vals),unknown_platform=0,incomplete=sum(t and not c for t,c,h in vals))
    for key,v in exp.items():
        if key in row and int(row[key]) != v:
            out['mismatches'].append([mode,filename,rownum,key,row[key],v])
    ratecol, scale = ('rate',1) if mode == 'A' else ('pct',100)
    if ratecol in row:
        actual = row[ratecol]
        if (n == 0 and actual != '') or (n and (actual == '' or abs(float(actual)-scale*k/n)>1e-10)):
            out['mismatches'].append([mode,filename,rownum,ratecol,actual,scale*k/n if n else None])
    out['checks'][mode+':'+filename] = out['checks'].get(mode+':'+filename,0)+1

for mode, periods, metrics in [('A',PA,MA),('B',PB,MB)]:
    C = RAW / mode / 'case/calculations'
    filenames = ['periods.csv','segments.csv', 'cohorts.csv' if mode=='A' else 'weekly.csv',
                 'early_behaviors.csv' if mode=='A' else 'activation_associations.csv']
    for fn in filenames:
        for line,r in enumerate(rows(C/fn),2):
            ws = periods[r['period']] if 'period' in r else [r.get('cohort_week',r.get('cohort'))]
            pop = [u for u in users if u['cohort_week'] in ws]
            if fn == 'segments.csv':
                dim = r['dimension']; value = r.get('value', r.get('segment'))
                def key(u):
                    if dim=='channel_platform': return (u['channel'] or 'unknown')+'|'+u['platform']
                    return u[dim] or ('(missing)' if mode=='A' else 'unknown')
                pop = [u for u in pop if key(u)==value]
            elif fn == 'early_behaviors.csv':
                pop = [u for u in pop if complete(u,0,2) and feature(u,r['feature']) == (r['value']=='True')]
            elif fn == 'activation_associations.csv':
                pop = [u for u in pop if complete(u,0,3) and str(activation(u,r['activation']))==r['value']]
            check(mode,fn,line,r,pop,r['metric'])
    # Activation frequencies checked independently in their own early window.
    fn = 'activation_rates.csv' if mode=='A' else 'activation.csv'
    for line,r in enumerate(rows(C/fn),2):
        pop = [u for u in users if u['cohort_week'] in periods[r['period']] and complete(u,0,2 if mode=='A' else 3)]
        if mode=='A':
            if r['dimension']!='all': pop=[u for u in pop if (u[r['dimension']] or '(missing)')==r['value']]
            k=sum(feature(u,r['feature']) for u in pop)
        else:
            f=r['definition']
            if f.startswith('legacy='):
                terms=dict(t.split('=') for t in f.split('|'))
                k=sum(all(str(activation(u,key))==value for key,value in terms.items()) for u in pop)
            else: k=sum(activation(u,f) for u in pop)
        n=len(pop)
        if (int(r['k']),int(r['n']))!=(k,n): out['mismatches'].append([mode,fn,line,'k/n',r['k']+'/'+r['n'],f'{k}/{n}'])
        rate=r.get('rate',r.get('pct'))
        if n and abs(float(rate)-(1 if mode=='A' else 100)*k/n)>1e-10:out['mismatches'].append([mode,fn,line,'rate',rate])
        out['checks'][mode+':'+fn]=out['checks'].get(mode+':'+fn,0)+1
    for day in (7,30):
        m=f'D{day}_'+('completed' if mode=='A' else 'complete')
        vals=[cache[mode,m,u['user_id']] for u in users]
        out['balance'][mode+':D'+str(day)]={'total':len(vals),'immature':sum(not t for t,c,h in vals),'incomplete':sum(t and not c for t,c,h in vals),'n':sum(c for t,c,h in vals),'k':sum(c and h for t,c,h in vals)}
    # Main report k/n cells, counted once per stated period and outcome.
    selected = [('early_3','D7_completed'),('later_3','D7_completed'),('early_3','D30_completed'),('later_3','D30_completed'),('early_3','D7_open'),('later_3','D7_open'),('early_3','D30_open'),('later_3','D30_open')] if mode=='A' else [('early_June','D7_complete'),('latest_D7','D7_complete'),('early_June','D30_complete'),('late_mature','D30_complete'),('late_mature','D7_complete')]
    out['main'][mode]=[r for r in rows(C/'periods.csv') if (r['period'],r['metric']) in selected]

# Sensitivity differences for B: check k/n and delta, not just recomputation of final tables.
for line,r in enumerate(rows(RAW/'B/case/calculations/sensitivity.csv'),2):
    computed=[]
    for suffix,period in [('0',r['p0']),('1',r['p1'])]:
        vals=[cache['B',r['metric'],u['user_id']] for u in users if u['cohort_week'] in PB[period]]
        n=sum(c for t,c,h in vals); k=sum(c and h for t,c,h in vals); computed.append((k,n))
        if (k,n)!=(int(r['k'+suffix]),int(r['n'+suffix])):out['mismatches'].append(['B','sensitivity.csv',line,suffix])
    if all(n for k,n in computed):
        delta=100*(computed[1][0]/computed[1][1]-computed[0][0]/computed[0][1])
        if abs(float(r['delta_pp'])-delta)>1e-10:out['mismatches'].append(['B','sensitivity.csv',line,'delta'])
    out['checks']['B:sensitivity.csv']=out['checks'].get('B:sensitivity.csv',0)+1

# Published A paired windows use the SAME eligibility for exact-day and wider outcomes.
for line,r in enumerate(rows(RAW/'A/case/calculations/paired_window_sensitivity.csv'),2):
    ws=weeks[:2] if r['period']=='early_2' else weeks[3:5]
    a,b=(6,8) if r['eligibility_window']=='D6_8' else (28,32)
    pop=[u for u in users if u['cohort_week'] in ws and complete(u,a,b)]
    x,y=(a,b) if r['metric']=='window' else ((7,7) if a==6 else (30,30))
    k=sum(event(u,x,y,{'task_completed'}) for u in pop)
    if (k,len(pop))!=(int(r['k']),int(r['n'])):out['mismatches'].append(['A','paired_window_sensitivity.csv',line])
    out['checks']['A:paired_window_sensitivity.csv']=out['checks'].get('A:paired_window_sensitivity.csv',0)+1

for pn,ws in [('June1_21',weeks[:3]),('June22_July12',weeks[3:6]),('June1_14',weeks[:2]),('June29_July12',weeks[4:6]),('July20_Aug2',weeks[7:9])]:
    result={}
    for day in (7,30):
        vals=[cache['A',f'D{day}_completed',u['user_id']] for u in users if u['cohort_week'] in ws]
        n=sum(c for t,c,h in vals);k=sum(c and h for t,c,h in vals)
        result['D'+str(day)]={'k':k,'n':n,'pct':100*k/n if n else None}
    out['common_periods'][pn]=result

# Check every published decomposition against raw-data group sizes and outcomes.
for mode in ('A','B'):
    for line,r in enumerate(rows(RAW/mode/'case/calculations/decomposition.csv'),2):
        if mode=='A':
            p0,p1='early_3','later_3'; periods=PA; dims=r['dimensions'].split('+')
        else:
            p0,p1=r['p0'],r['p1'];periods=PB
            dims=['channel','platform'] if r['dimension']=='channel_platform' else [r['dimension']]
        groups=[]
        for period in (p0,p1):
            g=defaultdict(lambda:[0,0])
            for u in users:
                if u['cohort_week'] in periods[period]:
                    t,c,h=cache[mode,r['metric'],u['user_id']]
                    if c:
                        key=tuple(u[d] for d in dims);g[key][0]+=1;g[key][1]+=h
            groups.append(g)
        a,b=groups; n0=sum(v[0] for v in a.values());n1=sum(v[0] for v in b.values())
        assert a.keys()==b.keys()
        vals=[(a[k][0]/n0,b[k][0]/n1,a[k][1]/a[k][0],b[k][1]/b[k][0]) for k in a]
        if mode=='A':
            exp={'within_delta':sum(w0*(y-x) for w0,w1,x,y in vals),
                 'composition_delta':sum((w1-w0)*y for w0,w1,x,y in vals),
                 'later_standardized':sum(w0*y for w0,w1,x,y in vals)}
        else:
            exp={'mix_pp':100*sum((w1-w0)*x for w0,w1,x,y in vals),
                 'within_pp':100*sum(w1*(y-x) for w0,w1,x,y in vals),
                 'std_delta_pp':100*sum((w0+w1)/2*(y-x) for w0,w1,x,y in vals)}
        for field,value in exp.items():
            if abs(float(r[field])-value)>1e-10:out['mismatches'].append([mode,'decomposition.csv',line,field])
        out['checks'][mode+':decomposition.csv']=out['checks'].get(mode+':decomposition.csv',0)+1

target=RAW/'numeric-checks.json'
target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
(RAW/'numeric-checks.sha256').write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'  numeric-checks.json\n')
print(json.dumps({'checks':out['checks'],'mismatches':out['mismatches'],'balance':out['balance']},ensure_ascii=False,indent=2))
assert not out['mismatches']
