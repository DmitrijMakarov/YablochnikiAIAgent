"""Учебные сценарии, не фактические результаты. Python standard library only.
Run from repo: .venv/bin/python cases/megafon-official/analysis/model.py
Money stored in rubles, cohorts in distinct index numbers, calendar months 1..12.
"""
import json, math, hashlib
from pathlib import Path
from statistics import NormalDist
P=Path(__file__).resolve().parent
inputs={
 'source_sha256':hashlib.sha256((P.parent/'inputs/brief.pdf').read_bytes()).hexdigest(),
 'brief':{'market_households':300000,'available_households':100000,'market_owners':180000,'available_owners':40000,'margin_rub_per_paid_number_month':500,
 'kpi':{'gp_rub':[282000000,275000000,279000000,285000000],'active_groups':[5000,4000,5000,8000],'connected_groups':[7500,6500,8000,12000],'connected_owners':[1000,800,1000,2000],'activation_14d':[.50,.42,.45,.60]}},
 'assumptions':{
 'baseline_new':2500,'baseline_exit':1000,'baseline_created':5000,
 'main':{'reach':40000,'created':10000,'new':6500,'exit':1000,'increment_active_rate':.75,'q4_created':2500,'q4_activated':1500,'cohorts':{'7':3000,'8':3000,'9':2000,'10':2000},'paid_delta_per_age_month':.01,'direct_by_quarter':[0,60000,120000,180000], 'investment_by_quarter':[230000,1370000,0,0],'annual_direct_after_year1':720000},
 'adverse':{'reach':24000,'created':6800,'new':3880,'exit':1000,'increment_active_rate':.5,'q4_created':1700,'q4_activated':850,'cohorts':{'9':1500,'10':1500,'11':1000,'12':1000},'paid_delta_per_age_month':.003,'direct_by_quarter':[0,60000,90000,150000],'investment_by_quarter':[230000,1370000,0,0],'annual_direct_after_year1':600000},
 'baseline_survival_by_age':[.95,.92,.89,.86,.83,.80],
 'pilot':{'p_control':.12,'p_treatment':.09,'practical_threshold':.02,'alpha_two_sided':.05,'n_each':1800,'recruit_weeks':6,'maturation_days':7,'cleaning_days':7,'operation_missing_max':.01,'donor_harm_margin':.02,'donor_base':.05}}}
def scenario(name):
 a=inputs['assumptions'];s=a[name]; rows=[];qmonths=[0.0]*4
 for start,n in s['cohorts'].items():
  for month in range(int(start),13):
   age=month-int(start); p0=a['baseline_survival_by_age'][min(age,5)]
   delta=s['paid_delta_per_age_month']*(min(age,5)+1)
   assert 0 <= p0 <= p0+delta <= 1
   add=n*delta;qmonths[(month-1)//3]+=add
   rows.append({'start_month':int(start),'calendar_month':month,'age_month':age,'index_numbers':n,'p_paid_control':p0,'p_paid_treatment':p0+delta,'additional_paid_number_months':add})
 new=s['new'];end=6500+new-s['exit'];inc=end-8000
 quarters=[{'quarter':i+1,'additional_paid_number_months':qmonths[i],'margin_rub':qmonths[i]*500,'direct_rub':s['direct_by_quarter'][i],'net_gp_rub':qmonths[i]*500-s['direct_by_quarter'][i],'investment_rub':s['investment_by_quarter'][i]} for i in range(4)]
 net=sum(q['net_gp_rub'] for q in quarters); invest=sum(s['investment_by_quarter'])
 yearly2=sum(s['cohorts'].values())*s['paid_delta_per_age_month']*6*12*500-s['annual_direct_after_year1']
 residual=invest-net;payback=None if yearly2<=0 else 12+residual/(yearly2/12)
 return {'connected_groups':end,'increment_groups':inc,'active_groups':5000+inc*s['increment_active_rate'],'owners':1000,'activation_14d':s['q4_activated']/s['q4_created'], 'additional_paid_number_months':sum(qmonths),'direct_rub':sum(s['direct_by_quarter']),'incremental_gp_rub':net,'gp_rub':279000000+net,'investment_rub':invest,'payback_month_from_year_start':payback,'year2_net_gp_conditional':yearly2,'max_recoverable_investment_year1':max(0,net),'cohort_rows':rows,'quarters':quarters}
res={k:scenario(k) for k in ['main','adverse']}
# Independent expected arithmetic constraints on stock, money and units.
assert res['main']['connected_groups']==12000
assert res['adverse']['connected_groups']==9380
assert math.isclose(res['main']['additional_paid_number_months'],1400)
assert math.isclose(res['adverse']['additional_paid_number_months'],84)
assert math.isclose(res['main']['gp_rub'],279340000)
assert math.isclose(res['adverse']['gp_rub'],278742000)
# Primary power: normal approximation, independent randomized groups, one index number/group.
p=inputs['assumptions']['pilot'];n=p['n_each'];nd=NormalDist();z=nd.inv_cdf(.975)
def power(p0,p1,n,threshold):
 se=math.sqrt((p0*(1-p0)+p1*(1-p1))/n); d=p0-p1
 crit=max(z*se,threshold)
 return {'se':se,'power_against_zero':1-nd.cdf(z-d/se)+nd.cdf(-z-d/se), 'prob_primary_full_rule':1-nd.cdf((crit-d)/se)}
primary=power(.12,.09,n,.02)
# Guardrail donor noninferiority: one-sided upper 95% bound on harm <2pp, true harm=0.
se_g=math.sqrt(2*.05*.95/n);prob_guard=nd.cdf(.02/se_g-nd.inv_cdf(.95))
zero_upper=1-.05**(1/n)
# Under unknown metric dependence, Frechet lower and upper bounds, not products.
primary['donor_guard_pass_probability_at_zero_harm']=prob_guard
primary['joint_primary_donor_frechet_bounds']=[max(0,primary['prob_primary_full_rule']+prob_guard-1),min(primary['prob_primary_full_rule'],prob_guard)]
primary['zero_incidents_upper_one_sided_95']=zero_upper
primary['full_success_probability']='unknown: consent/security, operation SLA, false alarms and completeness need calibration'
primary['n_each_approx_80pct_zero_test']=math.ceil(((z*math.sqrt(2*.105*.895)+nd.inv_cdf(.8)*math.sqrt(.12*.88+.09*.91))/.03)**2)
primary['flow_per_week']=2*n/6
primary['sensitivity']={str(e):power(.12,.12-e,n,.02) for e in [.01,.02,.03,.04]}
res['pilot']=primary
res['thresholds']={'gp_target_paid_months_main':(6000000+res['main']['direct_rub'])/500,'investment_recovery_paid_months_main':(res['main']['investment_rub']+res['main']['direct_rub'])/500,'gp_target_paid_months_adverse':(6000000+res['adverse']['direct_rub'])/500,'main_cac_per_increment_group':120000/4000}
# At fixed cohort sizes/timing and baseline survival, even p_treatment=1 caps effects.
res['thresholds']['max_paid_months_fixed_main_cohorts']=sum(r['index_numbers']*(1-r['p_paid_control']) for r in res['main']['cohort_rows'])
res['thresholds']['max_gp_fixed_main_cohorts']=279000000+500*res['thresholds']['max_paid_months_fixed_main_cohorts']-360000
(P/'inputs.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n')
(P/'results.json').write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n')
# Sensitivity: same cohorts, signed retention increments, cost and calendar shift.
sensitivity=[]
for scenario_name in ['main','adverse']:
 s=inputs['assumptions'][scenario_name]
 for multiplier in [0,.5,1,2]:
  months=res[scenario_name]['additional_paid_number_months']*multiplier
  sensitivity.append({'scenario':scenario_name,'retention_multiplier':multiplier,'additional_paid_number_months':months,'net_gp_rub':months*500-res[scenario_name]['direct_rub']})
for delay in [1,2,3]:
 s=inputs['assumptions']['main'];months=sum(n*.01*(m-(int(start)+delay)+1) for start,n in s['cohorts'].items() for m in range(int(start)+delay,13))
 sensitivity.append({'scenario':'main','delay_months':delay,'additional_paid_number_months':months,'net_gp_rub':months*500-360000})
(P/'sensitivity.json').write_text(json.dumps(sensitivity,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:{kk:vv for kk,vv in v.items() if kk not in ['cohort_rows']} for k,v in res.items()},ensure_ascii=False,indent=2))
