from pathlib import Path
import json,csv,math
P=Path(__file__).resolve().parent
r=json.loads((P/'analysis-results.json').read_text()); out=[]
def fmt(m):return f"{m['k']}/{m['n']} ({m['pct']:.2f}%)" if m['n'] else 'не созрела'
out+=['# Расчёты по синтетическим данным','', 'Воспроизведение из корня: `python3 cases/retention-demo/analyze.py`, затем `python3 cases/retention-demo/summarize.py`. Входные SHA-256, версия Python, проверки и все срезы — analysis-results.json. Части событий побайтно по CSV-полям сопоставлены с оригиналом; см. split-map.json.','', '## Удержание','', '| Когорта | N | D7 | исключено | D30 | исключено | W7 | W30 |','|---|---:|---|---:|---|---:|---|---|']
for c,v in r['cohorts'].items():out.append(f"|{c}|{v['size']}|{fmt(v['D7']['value'])}|{v['D7']['value']['excluded']}|{fmt(v['D30']['value'])}|{v['D30']['value']['excluded']}|{fmt(v['W7']['value'])}|{fmt(v['W30']['value'])}|")
out+=['','Частичные знаменатели показаны диагностически. Межкогортный вывод делаем только по full_cohorts для конкретной метрики: исключённые платформы и даты регистрации могут менять состав.', '', '## Активация и напоминания','', 'Пул только полностью наблюдаемых когорт для каждой метрики; дополнительно требуются complete D0 и D1. D0–D1 — календарные дни, не 48 часов.','', '| Признак D0–D1 / значение | D7 | D30 |','|---|---|---|']
for section in ['activation','reminders']:
 for g in sorted(set('/'.join(k.split('/')[1:]) for k in r[section])):
  cells=[]
  for m in ['D7','D30']:
   vs=[v[m] for k,v in r[section].items() if '/'.join(k.split('/')[1:])==g and k.split('/')[0] in r['full_cohorts'][m]]
   n=sum(v['n'] for v in vs); k=sum(v['k'] for v in vs); cells.append(f'{k}/{n} ({100*k/n:.2f}%)' if n else '—')
  out.append('|'+section+'/'+g+'|'+'|'.join(cells)+'|')
out+=['','## Проверка неопределённости','']
a=r['cohorts']['2026-06-01']['D7']['value']; b=r['cohorts']['2026-07-27']['D7']['value']; p=a['k']/a['n']; q=b['k']/b['n']; d=q-p; se=math.sqrt(p*(1-p)/a['n']+q*(1-q)/b['n'])
out.append(f'D7, последняя полная против первой: {100*d:.2f} п.п.; приближённый 95% интервал разности [{100*(d-1.96*se):.2f}; {100*(d+1.96*se):.2f}] п.п. Нормальная аппроксимация независимых аккаунтов, без поправки на множественные сравнения; не доказательство равенства и не причинный эффект.')
out+=['','## Сценарий эксперимента','']
# Conservative two-arm normal approximation, p=.30, target +.05, alpha=.05 two-sided, power=.80.
p=.30;q=.35;m=(p+q)/2
n=math.ceil((1.96*math.sqrt(2*m*(1-m))+.84*math.sqrt(p*(1-p)+q*(1-q)))**2/(q-p)**2)
out.append(f'Для двух групп, p0=30%, p1=35%, alpha=5% двусторонняя, мощность 80%: n=ceil(((1.96*sqrt(2*pbar*(1-pbar))+.84*sqrt(p0*(1-p0)+p1*(1-p1))) / .05)^2)={n} на группу. Это плановое допущение; после проверки живой базовой частоты пересчитать до запуска. При 10% резерве ceil({n}/.9)={math.ceil(n/.9)} назначений на группу. Исторический синтетический темп 3020/10=302 регистрации/неделю не является прогнозом трафика; при таком условном темпе набор займёт {2*math.ceil(n/.9)/302:.1f} недели, затем минимум 34 дня на окно W30 последнего аккаунта. Не подменять отсутствующие результаты нулями.')
(P/'analysis.md').write_text('\n'.join(out)+'\n')
