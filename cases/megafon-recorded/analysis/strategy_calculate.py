"""Local reproducible sensitivity, stdlib only; no real client observations."""
import csv
import hashlib
import json
import math
import platform
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / 'analysis'
params = json.loads((A / 'strategy_parameters.json').read_text())
normal = NormalDist()
z = normal.inv_cdf(1 - params['primary_one_sided_alpha'])
zg = normal.inv_cdf(1 - params['guardrail_alpha'])

def primary(p, d, n):
    q = p - d
    se = math.sqrt((p * (1-p) + q * (1-q)) / n)
    critical = z * se
    return {'se': se, 'power_vs_zero': normal.cdf(d / se - z),
            'prob_primary_rule': normal.cdf((d - max(critical, params['practical_threshold'])) / se)}

def guard(base, margin, n, harm=0):
    se = math.sqrt((base*(1-base)+(base+harm)*(1-base-harm))/n)
    return normal.cdf((margin-harm)/se-zg)

# Recheck existing checkpointed auxiliary files without altering them.
manifest = json.loads((A / 'manifest.json').read_text())
hash_checks = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == expected
               for p, expected in manifest['files'].items()}
assert all(hash_checks.values()), 'research auxiliary hash mismatch'
source = json.loads((A / 'inputs.json').read_text())
v = {k: x['values'] for k, x in source['metrics'].items()}
gaps = {k: x[3]-x[2] for k, x in v.items()}
assert gaps['gross_profit_rub'] == 6_000_000
assert 100 * 2 * 500 == 100_000
assert 12_000 * (5_000/8_000) == 7_500
assert (7_500-5_000)+(8_000-7_500) == 3_000
assert math.isclose(30/100, .3)

rows=[]
for p in params['primary_control_risks']:
    for d in params['true_benefits']:
        for n in params['n_per_arm']:
            x=primary(p,d,n)
            gs=[guard(g['baseline'], g['margin'], n) for g in params['guardrails']]
            probs=[x['prob_primary_rule'], *gs]
            rows.append({'control_risk':p,'true_benefit':d,'n_per_arm':n,**x,
                         'normal_approximation_sparse_warning':min(n*p,n*(p-d),n*.002)<10,
                         'prob_G1_no_harm_scenario':gs[0], 'prob_G2_no_harm_scenario':gs[1],
                         'covered_conjunction_lower':max(0,sum(probs)-(len(probs)-1)),
                         'covered_conjunction_upper':min(probs),
                         'full_rule_lower':0, 'full_rule_upper':min(probs),
                         'new_families_per_week_for_6_week_enrolment':math.ceil(2*n/6)})

required=[]
for p in params['primary_control_risks']:
    # Allocate 0.10 total failure budget equally across primary + G1 + G2;
    # union bound works without assuming independence. Still excludes G3–G6.
    n=1
    while True:
        probs=[primary(p,.045,n)['prob_primary_rule']]+[
            guard(g['baseline'],g['margin'],n) for g in params['guardrails']]
        if min(probs)>=1-.1/3:
            break
        n+=1
    required.append({'control_risk':p,'n_per_arm':n,'covered_rule_lower':1-sum(1-x for x in probs),
                     'families_per_week_6_weeks':math.ceil(2*n/6)})

guard_sizes=[]
for g in params['guardrails']:
    n=math.ceil(2*g['baseline']*(1-g['baseline'])*
                (zg+normal.inv_cdf(.9))**2 / g['margin']**2)
    guard_sizes.append({**g,'n_per_arm_for_90pct_no_harm_scenario':n,
                        'pass_probability_if_true_harm_equals_margin':guard(g['baseline'],g['margin'],n,g['margin'])})
rare_n=math.ceil(math.log(params['zero_event_alpha'])/math.log(1-params['zero_event_max_risk']))
rare={'required_exposures_if_zero_events':rare_n,
      'upper95_if_zero_in_300':1-.05**(1/300),
      'upper95_if_zero_in_required':1-.05**(1/rare_n),
      'note':'Binomial independent exposures only; clustering needs new calculation; applies separately to revocations/operations.'}
assert rare_n==2995

economics=[]
for s in params['economics']:
    m=s['exposed_numbers']*s['months_in_year']*s['paid_probability_lift']
    net=500*m-s['direct_cost_rub']
    economics.append({**s,'additional_paid_number_months':m,'incremental_gross_profit_rub':net,
                      'year_profit_rub':279_000_000+net,
                      'gap_to_target_rub':max(0,6_000_000-net),
                      'max_development_repaid_by_year_end_rub':max(0,net),
                      'net_after_development_rub':net-s['development_rub'],
                      'required_lift_for_annual_target':(6_000_000+s['direct_cost_rub'])/(500*s['exposed_numbers']*s['months_in_year'])})

out={'python':platform.python_version(),'method':'normal planning approximation with true-variance SE; no empirical estimates',
     'input_sha256':hashlib.sha256((A/'strategy_parameters.json').read_bytes()).hexdigest(),
     'research_auxiliary_hashes_all_match':all(hash_checks.values()),'recomputed_annual_gaps':gaps,
     'sample_sensitivity':rows,'covered_rule_required':required,'guardrail_sizes':guard_sizes,
     'zero_event_bound':rare,'economics':economics,
     'uncovered':['G3 false alerts','G4 missingness and worst-case CI','G5/G6 event probability and clustering','system readiness','cost and retention evidence'],
     'simulation_error':'not applicable: analytic approximation, no Monte Carlo',
     'full_rule_sample_justified':False}
(A/'strategy_results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
lines=['# Расчёт стратегии: сценарии, не данные','',
       'Команда: `.venv/bin/python cases/local/megafon-video/analysis/strategy_calculate.py`.',
       'Входы: `strategy_parameters.json`; паспорта: `strategy_metrics.md`. Все новые вероятности, частоты и расходы проектные.',
       'Python '+platform.python_version()+'. Нормальная аналитическая аппроксимация с SE при истинных рисках. Это не точный тест и не эмпирический эффект.',
       'При ожидаемых событиях <10 приближение особенно ненадёжно (например, G2 при N=300/2000 и primary p0=5%, Δ=4,5 п.п., N=300). Такие ячейки помечены в JSON и не дают достаточного размера выборки.',
       '','## Проверки исходного исследования',str(gaps),
       'Все хеши research manifest совпали; независимые примеры 100×2×500=100000, 30/100=30%, 2500+500=3000 проверены.',
       '','## Primary при сценарной базе 12%',
       '| N в плече | Истинная польза | Мощность против 0 | Вероятность primary+порог | G1 | G2 | Границы primary∩G1∩G2 |',
       '|---:|---:|---:|---:|---:|---:|---:|']
for r in rows:
    if r['control_risk']==.12:
        lines.append(f"| {r['n_per_arm']} | {r['true_benefit']:.1%} | {r['power_vs_zero']:.1%} | {r['prob_primary_rule']:.1%} | {r['prob_G1_no_harm_scenario']:.1%} | {r['prob_G2_no_harm_scenario']:.1%} | {r['covered_conjunction_lower']:.1%}–{r['covered_conjunction_upper']:.1%} |")
lines+=['','При истинной пользе 3 п.п. большая выборка даёт около 50% пересечений практического порога, даже когда мощность против нуля близка к 100%.',
        'G1/G2 рассчитаны при истинном вреде 0. Зависимости неизвестны: границы Фреше max(0,ΣP−2), min(P), без перемножения вероятностей.',
        'Для полного правила, включая непокрытые условия, доказуемая из расчёта граница только [0; min(P_primary,P_G1,P_G2)].',
        '','## Выборка для покрытой части с нижней границей 90%',
        '| База primary | N/плечо | Нижняя граница | Семей/неделю при 6 неделях |','|---:|---:|---:|---:|']
for r in required:
    lines.append(f"| {r['control_risk']:.0%} | {r['n_per_arm']} | {r['covered_rule_lower']:.1%} | {r['families_per_week_6_weeks']} |")
lines+=['','При целевом истинном эффекте 4,5 п.п. каждому из трёх условий выделено ≤0,10/3 вероятности провала; граница объединения не требует независимости.',
        'Это не выборка для полного правила; необходимая база семей с первым событием неизвестна и не равна годовому числу подключений.',
        '','## Защитные метрики отдельно']
for r in guard_sizes:
    lines.append(f"- {r['name']}: база {r['baseline']:.1%}, предел вреда {r['margin']:.1%}, N/плечо для 90% прохождения при нулевом вреде ≈{r['n_per_arm_for_90pct_no_harm_scenario']}; если истинный вред равен пределу, шанс пройти ≈{r['pass_probability_if_true_harm_equals_margin']:.1%}.")
lines += [f"- При нуле событий нужно ≥{rare_n} независимых экспозиций отдельно для каждого редкого исхода, чтобы точная односторонняя верхняя 95% граница ≤0,1%. При 300 нулях верхний предел {rare['upper95_if_zero_in_300']:.3%}. События после отзывов и операции не имеют автоматически знаменатель N семей.",
          '- G3: сценарная частота 2% против лимита 5% требует отдельного биномиального расчёта после выбора реального знаменателя и полноты проверки; текущая выборка не подтверждена.',
          '- G4: нет эмпирической частоты/структуры пропусков; нужно считать крайние заполнения и их интервалы. Условие не покрыто мощностью.',
          '', '**Выборка не обоснована для полного правила успеха**. Не покрыты G3, G4, частоты/зависимости G5/G6, техническая готовность и экономика. Пересчитать до запуска, либо ограничить работу проверкой исполнения без заявления клиентской пользы.',
          '','## Экономическая чувствительность',
          '| Сценарий | M | Доп. валовая прибыль | Прибыль года | Разрыв до 285 млн | D max к концу года | Итог после D |',
          '|---|---:|---:|---:|---:|---:|---:|']
for r in economics:
    lines.append(f"| {r['name']} | {r['additional_paid_number_months']:g} | {r['incremental_gross_profit_rub']:g} | {r['year_profit_rub']:g} | {r['gap_to_target_rub']:g} | {r['max_development_repaid_by_year_end_rub']:g} | {r['net_after_development_rub']:g} |")
lines+=['','M=N×T×δ, δ — причинный прирост вероятности платного обслуживания в каждом доступном месяце. Упрощение постоянной δ и единой даты доступности; реальная модель требует помесячных когорт.',
        'Прибыль=279000000+500M−C; разработка D отдельно. D_max=max(0,500M−C), но отрицательный поток означает отсутствие окупаемости даже при D=0.',
        'Ни один сценарий не прогноз спроса. boundary_only — условие масштаба, не разрешение масштабировать. Денежные ставки команд неизвестны.',
        'Полная таблица p0=5/12/25% и Δ=1,5/3/4,5 п.п., N=300/2000/10000/25000 — в strategy_results.json.']
(A/'strategy_results.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'research_hashes_match':all(hash_checks.values()),'required_covered_only':required,
                  'guardrail_sizes':guard_sizes,'zero_event_n':rare_n,'economics':economics},ensure_ascii=False,indent=2))
