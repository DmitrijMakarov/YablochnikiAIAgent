import csv,pathlib
P=pathlib.Path(__file__).resolve().parent
rows=[]
for c in (600000,1200000,2400000):
 for d in (0,.01,.03,.05):
  n=7800;added=n*d;m=3000
  rows.append(dict(N_6months=n,delta_R30=d,total_cost_RUB=c,added_useful_D30=added,breakeven_margin_RUB=c/added if added else None,scenario_margin_RUB=m,incremental_margin_RUB=added*m,net_RUB=added*m-c))
with (P/'economics.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print('Scenario waiting cost',600*.03*3000,'break-even error probability reduction',(150000+54000)/1200000)
