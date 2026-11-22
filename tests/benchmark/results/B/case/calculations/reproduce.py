"""Re-run all calculations using fixed source hashes and local Python stdlib only."""
import pathlib,hashlib,json,subprocess,sys,time,datetime,platform,sqlite3
P=pathlib.Path(__file__).resolve().parent;C=P.parent
expected=json.loads((P/'input_versions.json').read_text())
for name,v in expected.items():
 f=C/'inputs'/name
 assert hashlib.sha256(f.read_bytes()).hexdigest()==v['sha256'],f'Input changed: {name}'
outputs=['weekly.csv','periods.csv','sensitivity.csv','segments.csv','decomposition.csv','activation.csv','activation_associations.csv','activation_users.csv','missing_by_cohort.csv','quality_data.json','experiment_scenarios.csv','reminder_strata.csv','platform_check.csv','economics.csv','independent_check.json']
previous={name:hashlib.sha256((P/name).read_bytes()).hexdigest() for name in outputs if (P/name).exists()}
runs=[]
for script in ('analysis.py','experiment.py','reminder_strata.py','platform_check.py','economics.py','independent_check.py'):
 start=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.monotonic()
 result=subprocess.run([sys.executable,str(P/script)],capture_output=True,text=True)
 (P/(script.removesuffix('.py')+'_stdout.txt')).write_text(result.stdout)
 if result.stderr:(P/(script.removesuffix('.py')+'_stderr.txt')).write_text(result.stderr)
 runs.append(dict(script=script,started_utc=start,seconds=time.monotonic()-t,returncode=result.returncode))
 if result.returncode:raise RuntimeError(f'{script} failed: {result.stderr}')
checks=[]
for name in outputs:
 sha=hashlib.sha256((P/name).read_bytes()).hexdigest();checks.append(dict(output=name,sha256=sha,matched_previous=previous.get(name)==sha))
assert all(r['matched_previous'] for r in checks),'Reproduction differs; inspect outputs'
report=dict(python=platform.python_version(),executable=sys.executable,sqlite=sqlite3.sqlite_version,runs=runs,output_checks=checks,source_hashes_matched=True,packages_installed=False,web_requests=0,model='unknown',tokens=None,cost=None)
(P/'reproduction_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
