"""Run only previously reviewed calculation commands in restored disposable copies.
Invoke under an OS sandbox with network denied; never run on raw archives.
"""
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(sys.argv[1]) if len(sys.argv)>1 else Path('/private/tmp')
report = {'network_probe':None,'runs':{}}
try:
    with socket.socket() as probe:
        probe.connect(('127.0.0.1', 9))
except PermissionError as e:
    report['network_probe'] = repr(e)
else:
    raise RuntimeError('network socket creation was not denied; refusing execution')
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
for mode in ('A','B'):
    p=BASE/f'megafon-final-review-{mode}'
    calc=p/'case/calculations'
    before={q.name:hashlib.sha256(q.read_bytes()).hexdigest() for q in calc.glob('*.csv')}
    commands = [['case/analyze.py'],['case/additional_analysis.py'],['case/sensitivity.py'],['case/verify_local.py']] if mode=='A' else [['case/calculations/reproduce.py'],['-m','tools.case','verify','case','--research-only'],['-m','tools.case','verify','case']]
    results=[]
    for n,cmd in enumerate(commands):
        t=time.monotonic()
        r=subprocess.run([sys.executable,*cmd],cwd=p,env=env,capture_output=True,text=True)
        (p/f'review-command-{n}.stdout').write_text(r.stdout)
        (p/f'review-command-{n}.stderr').write_text(r.stderr)
        results.append({'command':['python3',*cmd],'returncode':r.returncode,'seconds':time.monotonic()-t,'stdout':r.stdout,'stderr':r.stderr})
    checks={name:hashlib.sha256((calc/name).read_bytes()).hexdigest()==h for name,h in before.items()}
    report['runs'][mode]={'commands':results,'csv_matches':checks,'manual_corrections':0}
    assert all(checks.values()) and all(r['returncode']==0 for r in results)
target=BASE/'megafon-reproduction-check.json'
target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:{'commands':len(v['commands']),'csv_matches':sum(v['csv_matches'].values())} for k,v in report['runs'].items()}))
