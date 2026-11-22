import argparse,json
from .forecast import train,predict
p=argparse.ArgumentParser(); p.add_argument('command',choices=['train','predict']); p.add_argument('--target',choices=['y','demand','supply']); p.add_argument('--horizon',type=int,choices=[7,15,30]); p.add_argument('--as-of'); a=p.parse_args()
if a.command=='train': print(json.dumps(train(),ensure_ascii=False))
else:
 if not a.target or not a.horizon: p.error('predict requires --target and --horizon')
 print(json.dumps(predict(a.target,a.horizon,a.as_of),ensure_ascii=False))
