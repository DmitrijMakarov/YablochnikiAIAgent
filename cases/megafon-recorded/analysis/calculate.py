"""Reproduce descriptive arithmetic only; no strategy forecast or causal estimate."""
from pathlib import Path
from decimal import Decimal
import json, hashlib
from datetime import datetime, timezone
R=Path(__file__).resolve().parents[1]
p=R/'analysis/inputs.json'; x=json.loads(p.read_text())
v={k:[Decimal(str(z)) for z in obj['values']] for k,obj in x['metrics'].items()}
gaps={k:{'base_plan_minus_estimate':str(a-b),'next_target_minus_no_change':str(d-c),'unit':x['metrics'][k]['unit']} for k,(a,b,c,d) in v.items()}
A=v['active_groups_last_month']; N=v['connected_groups_year_end']; O=v['connected_owners_year_end']
r0=A[2]/N[2]; r1=A[3]/N[3]
threshold=v['gross_profit_rub'][3]-v['gross_profit_rub'][2]
rate=Decimal(x['paid_month_margin_rub'])
result={
'calculated_utc':datetime.now(timezone.utc).isoformat(),
'input_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
'original_pdf_sha256':hashlib.sha256((R/'inputs/brief.pdf').read_bytes()).hexdigest(),
'gaps':gaps,
'net_growth':{'households':{'target':str(N[3]-N[1]),'no_change':str(N[2]-N[1]),'incremental_gap':str(N[3]-N[2])},'owners':{'target':str(O[3]-O[1]),'no_change':str(O[2]-O[1]),'incremental_gap':str(O[3]-O[2])}},
'coverage_percent':{'households':[str(n/Decimal(x['accessible_base']['households'])*100) for n in N[1:]],'owners':[str(n/Decimal(x['accessible_base']['owners'])*100) for n in O[1:]]},
'active_decomposition':{'no_change_fraction':str(r0),'required_target_fraction':str(r1),'delta_pp':str((r1-r0)*100),'active_if_only_base_grows':str(N[3]*r0),'base_component':str((N[3]-N[2])*r0),'rate_component':str(A[3]-N[3]*r0),'sum':str(A[3]-A[2])},
'paid_month_threshold_no_other_contributions':str(threshold/rate),
'cost_sensitivity':[{'new_direct_cost_rub':c,'other_net_contribution_rub':0,'required_incremental_paid_months':str((threshold+Decimal(c))/rate),'nature':'illustrative assumption, not a cost estimate'} for c in x['illustrative_cost_sensitivity_rub']],
'controls':{'source_example_paid_margin_rub':100*2*int(rate),'source_example_activation':str(Decimal(30)/Decimal(100))},
'not_computable':['cause prevalence','segment mix versus within-segment dynamics','mature cohort comparison','statistical uncertainty','pilot power and full success probability','guardrail precision','effect on retention','CAC','development cost and payback date']}
assert result['controls']['source_example_paid_margin_rub']==100000
assert result['controls']['source_example_activation']=='0.3'
assert (N[3]-N[2])*r0 + (A[3]-N[3]*r0)==A[3]-A[2]
assert threshold/rate==12000
(R/'analysis/results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
(R/'analysis/results.md').write_text('''# Проверенные расчёты

Это описательная арифметика условий брифа, не прогноз стратегии. Вход: `analysis/inputs.json`, S-001@1 page:3 и page:9; контроль хешей и точные значения: `analysis/results.json`. Команда из корня репозитория: `.venv/bin/python cases/local/megafon-video/analysis/calculate.py`.

| Метрика | Базовый план | Базовая оценка | Недобор к базовому плану | Без изменений | Цель | Разрыв к будущей цели |
|---|---:|---:|---:|---:|---:|---:|
| Валовая прибыль, млн руб. | 282 | 275 | 7 | 279 | 285 | 6 |
| Активные группы, последний месяц | 5000 | 4000 | 1000 | 5000 | 8000 | 3000 |
| Подключённые группы, конец года | 7500 | 6500 | 1000 | 8000 | 12000 | 4000 |
| Подключённые владельцы, конец года | 1000 | 800 | 200 | 1000 | 2000 | 1000 |
| Активация за 14 дней, % | 50 | 42 | 8 п.п. | 45 | 60 | 15 п.п. |

Основания: [[C-005]], [[C-006]], [[C-007]], [[C-008]], [[C-009]]; выводы [[C-032]], [[C-033]].

## Потоки, охват и активность
Семьи: 12000−6500=5500 чистого прироста к цели; без изменений 8000−6500=1500; дополнительный разрыв 4000. Владельцы: 2000−800=1200, без изменений 1000−800=200, разрыв 1000. Это не валовые подключения: новые−ушедшие известны только как разность. [[C-034]] [[C-035]]

Охват доступной базы, оценка / без изменений / цель: семьи 6,5% / 8% / 12% от 100000 домохозяйств; владельцы 2% / 2,5% / 5% от 40000 владельцев. Не складывать группы, владельцев и SIM-карты. [[C-037]]

Для ровно 12000 подключённых целевая активность 8000/12000=66,6667%; без изменений 5000/8000=62,5%. При прежней доле 12000×0,625=7500: прирост базы даёт (12000−8000)×0,625=2500 активных, изменение доли — 8000−7500=500. Сумма 2500+500=3000, разность долей 4,1667 п.п. Это декомпозиция счётного тождества, не установленный механизм изменения. [[C-036]]

## Экономическая граница и чувствительность
ΔGP=500×M+O−C. Для цели ΔGP≥6000000: M≥max(0,(6000000+C−O)/500). M — дополнительные оплаченные номеро-месяцы внутри того же года; O — прочий чистый вклад без повторного учёта, C — новые прямые расходы, ещё не вошедшие в остальные слагаемые. Стоимость разработки сопоставляется с накопленной ΔGP отдельно. [[C-025]] [[C-026]] [[C-038]]

| Условные новые прямые расходы C, руб. | Прочий вклад O, руб. | Требуемые M |
|---:|---:|---:|
| 0 | 0 | 12000 |
| 1000000 | 0 | 14000 |
| 3000000 | 0 | 18000 |

Расходы 1 и 3 млн — произвольные точки чувствительности, не оценки стоимости и не предложение бюджета. Каждые дополнительные 1000 номеро-месяцев дают 500000 руб. до новых расходов. Ни число экспонированных номеров по месяцам, ни причинный прирост оплаченных месяцев, ни разработка не заданы. Поэтому достижимость границы, окупаемость и предельные вложения в рублях не установлены. Переносить эффект за границы года нельзя. [[C-031]] [[C-038]]

## Независимые контрольные примеры
1. Пример брифа page:9: 100 номеров × 2 месяца × 500 руб. = 100000 руб.; скрипт совпал с указанным итогом.
2. Пример page:3: 30 активированных / 100 созданных = 30%, а не 30/60=50%; приглашения без ответа остаются в знаменателе.
3. Декомпозиция активности проверена двумя путями: 8000−5000=3000 и 2500+500=3000.

Расчёты когорт, неопределённости, эффекта, цены привлечения и полной выборки не выполняются: нет необходимых входов. Дополнительные ограничения и паспорта — в `metrics.md`.
''',encoding='utf-8')
print(json.dumps({'gaps':gaps,'paid_month_threshold':str(threshold/rate),'controls':'passed'},ensure_ascii=False))
