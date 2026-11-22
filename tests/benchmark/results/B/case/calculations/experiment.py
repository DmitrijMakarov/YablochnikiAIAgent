"""Normal-approximation planning, explicit scenario inputs, dependence-free joint bounds."""
import csv, math, pathlib
P=pathlib.Path(__file__).resolve().parent
Phi=lambda x:(1+math.erf(x/math.sqrt(2)))/2
Z=1.959963984540054
# Design: primary D30 completed, p0=.18; positive two-sided 5% CI and estimate >=.03.
# Two harm metrics, upper one-sided 97.5% CI below margin (Bonferroni across 2).
# complaint baseline .005 margin .005; unwanted/disabled reminders baseline .10 margin .02.
# Baselines for guards are assumptions because absent in export. All accounts denominator.
def primary(n,d):
 p=.18;q=p+d;se=math.sqrt((p*(1-p)+q*(1-q))/n)
 power=Phi(d/se-Z);practical=Phi((d-max(.03,Z*se))/se)
 return power,practical

def guard(n,p,delta,margin):
 q=p+delta;se=math.sqrt((p*(1-p)+q*(1-q))/n)
 return Phi((margin-delta)/se-Z)
def row(n,d,g1,g2):
 power,practical=primary(n,d);p1=guard(n,.005,g1,.005);p2=guard(n,.10,g2,.02)
 return dict(n_per_arm=n,true_primary_pp=100*d,true_complaint_harm_pp=100*g1,true_unwanted_harm_pp=100*g2,power_vs_zero=power,primary_rule_probability=practical,complaint_pass_probability=p1,unwanted_pass_probability=p2,full_rule_lower_bound=max(0,practical+p1+p2-2),full_rule_upper_bound=min(practical,p1,p2),weeks_at_300_signups=2*n/300+34/7)
rows=[row(n,d,g1,g2) for n in (500,1000,2000,4000,6000,8000,12000) for d in (0,.03,.05) for g1,g2 in ((0,0),(.0025,.01))]
with (P/'experiment_scenarios.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
for harm in ((0,0),(.0025,.01)):
 for n in range(100,100001,10):
  r=row(n,.05,*harm)
  if r['full_rule_lower_bound']>=.8:print('n for guaranteed lower bound .80 under normal scenario:',r);break
for r in rows:
 if r['n_per_arm'] in (1000,2000,6000) and r['true_primary_pp'] in (3,5) and r['true_complaint_harm_pp']==0:print(r)
# Individual 80% pass sizes at no harm; guard assumptions vary as sensitivity.
for label,p,margin in [('complaints',.005,.005),('unwanted',.10,.02),('complaints higher base',.02,.005),('unwanted higher base',.20,.02)]:
 n=math.ceil(2*p*(1-p)*(Z+.8416212335729143)**2/(margin**2));print('guard80',label,n)
