"""Independent Decimal recomputation; does not import model.py."""
from decimal import Decimal as D
from pathlib import Path
import json
P=Path(__file__).resolve().parent
r=json.loads((P/'results.json').read_text())
# Alternative calendar-first summation, fixed literal assumptions rather than model functions.
checks={}
for name,cohorts,step,cost in [('main',[(7,3000),(8,3000),(9,2000),(10,2000)],D('.01'),360000),('adverse',[(9,1500),(10,1500),(11,1000),(12,1000)],D('.003'),300000)]:
 monthly=[]
 for month in range(1,13):
  monthly.append(sum((D(n)*step*D(month-start+1) for start,n in cohorts if start<=month),D(0)))
 paid=sum(monthly);profit=D(279000000)+paid*500-cost
 assert paid==D(str(r[name]['additional_paid_number_months']))
 assert profit==D(str(r[name]['gp_rub']))
 checks[name]={'calendar_monthly_number_months':[str(x) for x in monthly],'total_number_months':str(paid),'gp_rub':str(profit)}
assert 6500+6500-1000==12000
assert 6500+3880-1000==9380
assert 5000+4000*D('.75')==8000
assert 5000+1380*D('.5')==5690
assert 1500/D(2500)==D('.6') and 850/D(1700)==D('.5')
assert D(6000000+360000)/500==12720
assert D(1260000)/(D(2880000)/12)==D('5.25')
assert D(20000)*D('.25')*D('.65')*2==6500
assert D('.8')*D('.1875')+D('.2')*D('.0625')==D('.1625')
checks['verdict']='PASS: independent Decimal arithmetic; units rubles and paid number-months, not group-months.'
(P/'independent-check.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(checks,ensure_ascii=False,indent=2))
