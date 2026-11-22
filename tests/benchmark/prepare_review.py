"""Prepare strategy-only anonymized reading copies and factual archive audit.
Does not claim blind scoring; reviewer already knows the mapping.
"""
import csv
import difflib
import hashlib
import json
import re
import secrets
import shutil
from datetime import datetime
from pathlib import Path

HERE=Path(__file__).resolve().parent
OUT=HERE/'results'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((OUT/'archive-manifest.json').read_text())
audit={'registration_matches':all(e['matches'] for e in manifest['registered_materials'].values()),'runs':{},
       'reference_expected_bytes_equal':Path('/private/tmp/megafon-reference-check.json').read_bytes()==(HERE.parent/'fixtures/retention-expected/expected.json').read_bytes()}
for mode,run in manifest['runs'].items():
    c=OUT/mode/'case'
    a={'files':len(run['files']),'raw_bytes':sum(e['bytes'] for e in run['files'].values()),
       'archived_bytes':sum(e['bytes'] for e in run['files'].values() if 'repository_reference' not in e),
       'referenced_files':sum('repository_reference' in e for e in run['files'].values()),
       'missing_registered':run['missing_registered'],
       'changed_registered':[rel for rel,e in run['files'].items() if e.get('registered_matches') is False],
       'model_reported':'unknown','model_version':'unknown','effort_verified':'unknown','tokens':None,'cost':None,
       'wall_time_start_to_final_seconds':None,'human_minutes':None,'full_tool_trace_present':False}
    if mode=='A':
        a['local_hash_mismatches']={}
        for name in ('deliverable_hashes.json','calculation_hashes.json'):
            a['local_hash_mismatches'][name]=[f for f,h in json.loads((c/name).read_text()).items() if sha(c/f)!=h]
        actions=[json.loads(l) for l in (c/'actions.jsonl').read_text().splitlines()]
        times=[datetime.fromisoformat(r['timestamp_utc']) for r in actions]
        calls=list(csv.DictReader((c/'tool_calls.tsv').open(),delimiter='\t'))
        a.update(local_record_span_seconds=(max(times)-min(times)).total_seconds(),
                 self_recorded_tool_calls=len(calls),self_recorded_tool_errors=sum(r['status']=='error' for r in calls))
    else:
        state=json.loads((c/'state.json').read_text())
        a['checkpoint_hash_mismatches']=[phase+':'+f for phase,files in state['completed'].items() for f,h in files.items() if sha(c/f)!=h]
        rr=list(csv.DictReader((c/'run.tsv').open(),delimiter='\t'))
        a.update(state=state['status'],journal_rows=len(rr),journal_error_rows=sum(r['status']=='error' for r in rr),
                 nonagent_terminal_records=sum(r['tool']!='agent' and r['status']!='started' for r in rr),
                 phase_seconds={r['step']:float(r['seconds']) for r in rr if r['tool']=='agent' and r['status']=='ok'})
        times=[datetime.fromisoformat(r['started_utc']) for r in rr if r['started_utc']]+[datetime.fromisoformat(r['ended_utc']) for r in rr if r['ended_utc']]
        a['local_record_span_seconds']=(max(times)-min(times)).total_seconds()
        a['self_recorded_tool_calls']=None
    audit['runs'][mode]=a
(OUT/'provenance-checks.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
frozen=OUT/'registered'
frozen.mkdir(exist_ok=True)
for rel in ['registration.json',*json.loads((HERE/'registration.json').read_text())['files_sha256']]:
    dest=frozen/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(HERE/rel,dest)

anon=OUT/'anonymized'
assert not anon.exists(), 'refuse to remap existing anonymous copies'
anon.mkdir()
codes=secrets.SystemRandom().sample(['R-23','R-48','R-61','R-79'],2)
mapping={}
for mode,code in zip(('A','B'),codes):
    original=(OUT/mode/'case/strategy.md').read_text()
    neutral=original
    # Remove transport/process metadata only. Keep all arguments, assumptions and numbers.
    if mode=='A':
        start=neutral.index('Проверяемые основания R1–R13')
        neutral=neutral[:start]+'Основания R1–R13 и версии S-001@1–S-007@1 доступны в источниковом индексе у хранителя.\n'
    else:
        neutral=neutral.replace('Состояние кейса после проверки — ожидание решения, а не разрешение на запуск.', 'Рекомендация ожидает решения руководителя.')
        start=neutral.index('## Доказательства и воспроизведение')
        neutral=neutral[:start]+'Основания C-001–C-020 доступны в источниковом индексе у хранителя. Числа являются вычислениями по синтетике; публичные факты ограничены сохранёнными фрагментами.\n'
    neutral=re.sub(r'/Users/dima/strateg-benchmark-runs/[AB]', '[рабочий каталог]', neutral)
    # Reading copies must not accidentally navigate to unblinded originals.
    neutral=re.sub(r'\[([^\]]+)\]\((?!https?:)([^)]+)\)', lambda m:m[1]+' (`'+m[2]+'`)', neutral)
    dest=anon/(code+'.md');dest.write_text(neutral)
    mapping[code]={'mode':mode,'original':'../'+mode+'/case/strategy.md','original_sha256':sha(OUT/mode/'case/strategy.md'),
                   'anonymous_sha256':sha(dest),
                   'diff':''.join(difflib.unified_diff(original.splitlines(True),neutral.splitlines(True),fromfile='original',tofile=code))}
(OUT/'anonymization-map.json').write_text(json.dumps({'reviewer_blinded':False,'strategy_only':True,'mapping':mapping},ensure_ascii=False,indent=2)+'\n')
(anon/'README.md').write_text('Копии стратегий для чтения без меток режима и служебных сведений о процессе. Числа, аргументы и проектные допущения сохранены. Источниковые ссылки оставлены текстовыми локаторами: полный пакет доказательств выдаёт хранитель отдельно. Это не полный слепой экспертный пакет. Стиль и структура могут раскрыть методику. Текущий оценщик знает соответствие и не является слепым.\n')
print(json.dumps(audit,ensure_ascii=False,indent=2))
