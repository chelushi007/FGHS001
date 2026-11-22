import argparse,json
from .planner import optimize
p=argparse.ArgumentParser(description='Optimize simulated scrap transactions with OR-Tools')
p.add_argument('--role',choices=['steel_mill','recycler','individual'],required=True)
p.add_argument('--db',default='data/steelchain.sqlite'); p.add_argument('--party-id'); p.add_argument('--year',type=int); p.add_argument('--quota',type=float,default=5000000); p.add_argument('--transport-capacity-ton',type=float,default=100000)
a=p.parse_args()
print(json.dumps(optimize(a.role,a.db,a.party_id,a.year,transport_capacity_ton=a.transport_capacity_ton),ensure_ascii=False,indent=2))
