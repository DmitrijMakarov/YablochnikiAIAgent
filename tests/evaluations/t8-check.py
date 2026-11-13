"""Read-only T8 acceptance calculations; never imports or runs agent code.
Run from repository root: python3 tests/evaluations/t8-check.py
"""
import csv, hashlib, json, subprocess
from collections import defaultdict, Counter
from datetime import date, timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
R=ROOT/'tests/runs/t8-blind-2026-11-13'
I=ROOT/'cases/retention-demo/inputs'
def load(p): return json.loads(p.read_text())
def rows(p):
    with p.open(newline='') as f: return list(csv.DictReader(f, delimiter="\t" if p.suffix==".tsv" else ","))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
U=rows(I/'signups.csv'); E=rows(I/'events.csv'); C=rows(I/'coverage.csv')
A=load(R/'analysis-results.json'); X=load(ROOT/'tests/fixtures/retention-expected/expected.json')
cov={(r['event_date'],r['platform']):r['status'] for r in C}
seen={}; activity=defaultdict(set)
for e in E:
    if e['event_id'] in seen: assert seen[e['event_id']]==e
    seen[e['event_id']]=e
    activity[e['user_id'],e['event_date']].add(e['event_type'])
def day(u,d): return (date.fromisoformat(u['signup_date'])+timedelta(days=d)).isoformat()
def complete(u,ds): return all(cov.get((day(u,d),u['platform']))=='complete' for d in ds)
def hit(u,ds,types): return any(activity[u['user_id'],day(u,d)] & set(types) for d in ds)
def metric(us,ds,types):
    eligible=[u for u in us if complete(u,ds)]
    return {'k':sum(hit(u,ds,types) for u in eligible),'n':len(eligible)}
def pct(m): return 100*m['k']/m['n'] if m['n'] else None
weeks=sorted({u['cohort_week'] for u in U})
defs={'value':['task_created','task_completed'],'completion':['task_completed'], 'foreground':['app_open','task_created','task_completed','reminder_opened'],'any':list({e['event_type'] for e in E})}
wins={'D7':[7],'D30':[30],'W7':list(range(7,14)),'W30':list(range(28,35))}
checks=0
for w in weeks:
    us=[u for u in U if u['cohort_week']==w]
    for name,ds in wins.items():
        for typ,ts in defs.items():
            m=metric(us,ds,ts); saved=A['cohorts'][w][name][typ]
            assert (m['k'],m['n'])==(saved['k'],saved['n']), (w,name,typ,m,saved)
            checks+=1
    for age in (7,30):
        for typ,key in [('completion','task_completed')]:
            m=metric(us,[age],defs[typ]); ref=X['by_week'][w]['d'+str(age)]
            assert (m['k'],m['n'])==(ref[key],ref['eligible'])
segment_checks=0
for key,saved in A['segments'].items():
    week,field,v=key.split('/')
    sub=[u for u in U if u['cohort_week']==week and u[field]==v]
    for name,ds in wins.items():
        m=metric(sub,ds,defs['value'])
        assert (m['k'],m['n'])==(saved[name]['k'],saved[name]['n'])
        segment_checks+=1
for key,saved in A['activation'].items():
    week,field,v=key.split('/')
    def classify(u):
        if field=='legacy_setup_flag': return u[field]
        return str(hit(u,[0,1],['task_created'] if field=='activation_create' else defs['value']))
    sub=[u for u in U if u['cohort_week']==week and complete(u,[0,1]) and classify(u)==v]
    assert len(sub)==saved['size']
    for name in ('D7','D30'):
        m=metric(sub,wins[name],defs['value'])
        assert (m['k'],m['n'])==(saved[name]['k'],saved[name]['n'])
for key,saved in A['reminders'].items():
    week,v=key.split('/')
    sub=[u for u in U if u['cohort_week']==week and complete(u,[0,1]) and str(hit(u,[0,1],['reminder_enabled']))==v]
    assert len(sub)==saved['size']
    for name in ('D7','D30'):
        m=metric(sub,wins[name],defs['value'])
        assert (m['k'],m['n'])==(saved[name]['k'],saved[name]['n'])
periods={}
for label,ws in [('baseline',weeks[:3]),('recent',weeks[3:6])]:
    us=[u for u in U if u['cohort_week'] in ws]
    p={'size':len(us),'overall':{},'channel':{},'platform':{},'activation_groups':{}}
    for age in (7,30):
        p['overall']['D'+str(age)]={t:metric(us,[age],ts) for t,ts in {**defs,'open':['app_open']}.items()}
    for field in ('channel','platform'):
        for v in sorted({u[field] for u in us}):
            sub=[u for u in us if u[field]==v]; obs=[u for u in sub if complete(u,[0,1])]
            p[field][v or 'unknown']={'size':len(sub),'activation':{'k':sum(hit(u,[0,1],['task_created']) for u in obs),'n':len(obs)},'D7':metric(sub,[7],['task_completed']),'D30':metric(sub,[30],['task_completed'])}
    for v in ['created','not_created','unobservable']:
        sub=[u for u in us if ('unobservable' if not complete(u,[0,1]) else 'created' if hit(u,[0,1],['task_created']) else 'not_created')==v]
        p['activation_groups'][v]={f'D{d}':metric(sub,[d],['task_completed']) for d in (7,30)}
    periods[label]=p
standard={}
for d in ('D7','D30'):
    early=periods['baseline']['channel']; late=periods['recent']['channel']
    b=pct(periods['baseline']['overall'][d]['completion']); r=pct(periods['recent']['overall'][d]['completion'])
    fixed=sum(v[d]['n']/sum(z[d]['n'] for z in early.values())*pct(late[c][d]) for c,v in early.items())
    standard[d]={'baseline_pct':b,'recent_pct':r,'fixed_pct':fixed,'within_pp':fixed-b,'mix_pp':r-fixed,'total_pp':r-b}
    ref=X['channel_standardization'][d.lower()]
    assert abs(fixed/100-ref['recent_rate_baseline_mix'])<0.000001
# Verify all public snippets and structured table extracts against original rows.
evidence_checks={}
for sid,filename in [('S-002@1','signups.csv'),('S-004@1','coverage.csv')]:
    raw=list(csv.reader((I/filename).open()))
    ev=[json.loads(json.loads(s)['text']) for s in (R/f'evidence/{sid}.jsonl').read_text().splitlines()]
    assert raw==ev; evidence_checks[sid]=len(ev)-1
raw=list(csv.reader((I/'events.csv').open())); combined=[]
for part in load(R/'split-map.json')['parts']:
    ev=[json.loads(json.loads(s)['text']) for s in (R/f"evidence/{part['source']}.jsonl").read_text().splitlines()]
    assert ev[0]==raw[0]; combined+=ev[1:]
assert combined==raw[1:]
evidence_checks['event_parts']=len(combined)
for sid,filename in [('S-005@1','google-tasks.jsonl'),('S-006@1','microsoft-to-do.jsonl'),('S-007@1','todoist.jsonl')]:
    assert [json.loads(s) for s in (I/filename).read_text().splitlines()]==[json.loads(s) for s in (R/f'evidence/{sid}.jsonl').read_text().splitlines()]
product=(I/'product.md').read_text().splitlines()
for s in (R/'evidence/S-001@1.jsonl').read_text().splitlines():
    e=json.loads(s); assert product[int(e['locator'].split(':')[1])-1]==e['text']
for source in rows(R/'sources.tsv'):
    if source['status']=='available':
        assert sha(R/source['snapshot'])==source['sha256'], source['id']
checkpoints={f:sha(R/f)==h for phase in load(R/'state.json')['completed'].values() for f,h in phase.items()}
assert all(checkpoints.values())
archive=subprocess.run(['git','diff','--exit-code','a8ff9d424711de5b0ebe547127d3b05237728cc0','--','tests/runs/t8-blind-2026-11-13'],cwd=ROOT,capture_output=True)
assert archive.returncode==0
files=subprocess.check_output(['git','ls-tree','-r','--name-only','a8ff9d4','tests/runs/t8-blind-2026-11-13'],cwd=ROOT,text=True).splitlines()
assert sorted(files)==sorted(str(p.relative_to(ROOT)) for p in R.rglob('*') if p.is_file())
# Check saved synthetic control output without re-running generation or writing fixtures.
ref_run=subprocess.check_output(['python3','tests/fixtures/retention-expected/calculate.py',str(I)],cwd=ROOT,text=True)
assert json.loads(ref_run)==X
facts=[]
for c in rows(R/'claims.tsv'):
    if c['type']=='fact':
        ev={e['locator']:e['text'] for e in map(json.loads,(R/f"evidence/{c['source']}.jsonl").read_text().splitlines())}
        assert c['quote'] in ev[c['locator']]; facts.append(c['id'])
associations={}
for name in ('D7','D30'):
    pool=[u for u in U if u['cohort_week'] in A['full_cohorts'][name] and complete(u,[0,1])]
    associations[name]={}
    for kind,types in [('activation_create',['task_created']),('activation_value',defs['value']),('reminder',['reminder_enabled'])]:
        associations[name][kind]={str(v):metric([u for u in pool if hit(u,[0,1],types)==v],wins[name],defs['value']) for v in (False,True)}
out={'agent_cells_matched':checks,'segment_cells_matched':segment_checks,'reference_recomputed_exactly':True,'checkpoint_hashes':checkpoints,'archive_git_commit':'a8ff9d424711de5b0ebe547127d3b05237728cc0','archive_files_unchanged':len(files),'input_hashes':{p.name:sha(p) for p in sorted(I.iterdir())},'evidence_rows_matched':evidence_checks,'fact_quotes_present':facts,'periods':periods,'standardization':standard,'associations':associations,'activation_unobservable_retention':{f'D{d}':metric([u for u in U if not complete(u,[0,1])],[d],['task_completed']) for d in (7,30)},'activation_unobservable':sum(not complete(u,[0,1]) for u in U),'activation_definition_disagreements':sum(complete(u,[0,1]) and hit(u,[0,1],defs['value'])!=hit(u,[0,1],['task_created']) for u in U)}
print(json.dumps(out,ensure_ascii=False,indent=2))
