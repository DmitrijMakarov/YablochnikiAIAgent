"""Independent SQLite checks against raw source rows, no analysis module import."""
import csv,sqlite3,json,pathlib,hashlib
P=pathlib.Path(__file__).resolve().parent;I=P.parent/'inputs'
c=sqlite3.connect(':memory:')
for name in ('signups','events','coverage'):
 with (I/(name+'.csv')).open() as f:
  r=csv.reader(f);h=next(r);c.execute('create table '+name+' ('+','.join(x+' text' for x in h)+')');c.executemany('insert into '+name+' values ('+','.join('?' for _ in h)+')',r)
c.execute('create index event_lookup on events(user_id,event_date,event_type)')
c.execute('create index coverage_lookup on coverage(event_date,platform)')
out=[]
for cohorts in (('2026-06-01','2026-06-08'),('2026-06-29','2026-07-06'),('2026-07-20','2026-07-27')):
 for day in (7,30):
  n,k=c.execute('''select count(*),sum(exists(select 1 from events e where e.user_id=s.user_id and e.event_type='task_completed' and e.event_date=date(s.signup_date,?))) from signups s join coverage v on v.event_date=date(s.signup_date,?) and v.platform=s.platform where s.cohort_week in (?,?) and v.status='complete' ''',(f'+{day} day',f'+{day} day',*cohorts)).fetchone()
  k=k or 0
  period={('2026-06-01','2026-06-08'):'early_June',('2026-06-29','2026-07-06'):'late_mature',('2026-07-20','2026-07-27'):'latest_D7'}[cohorts]
  a=next(x for x in csv.DictReader(open(P/'periods.csv')) if x['period']==period and x['metric']==f'D{day}_complete')
  assert (n,k)==(int(a['n']),int(a['k']))
  out.append(dict(period=period,day=day,n=n,k=k,matched=True))
unique=c.execute('select count(distinct event_id) from events').fetchone()[0]
assert unique==83738
# Every chunk row is identical to the original, count and exact source hash retained.
raw=list(csv.DictReader(open(I/'events.csv')));chunk_n=0
for f in sorted(P.glob('events_rows_*.jsonl')):
 for line in f.open():
  r=json.loads(line);i=int(r['locator'].split(':')[1])-2;assert r['row']==raw[i];chunk_n+=1
assert chunk_n==len(raw)
result=dict(checks=out,distinct_event_ids=unique,chunk_rows_matched=chunk_n,source_sha256=hashlib.sha256((I/'events.csv').read_bytes()).hexdigest(),manual_examples=['D7 early: (69+94)/(242+275)=163/517=31.5280%', 'D30 late: (46+62)/(318+288)=108/606=17.8218%'])
(P/'independent_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
