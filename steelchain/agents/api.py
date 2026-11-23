from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import sqlite3
from pathlib import Path
import os
from steelchain.agents.graph import invoke
from steelchain.taxonomy import migrate_and_seed

DB=Path(os.environ.get('STEELCHAIN_DB',Path(__file__).resolve().parents[2]/'data'/'steelchain.sqlite'))
def ensure_simulated_database(path):
 path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
 con=sqlite3.connect(path)
 tables={row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 con.close()
 if not {'parties','categories','prices','offers','requirements'}.issubset(tables):
  if os.environ.get('STEELCHAIN_AUTO_SEED','1').lower() not in ('1','true','yes'):
   raise RuntimeError('database schema is not initialized and STEELCHAIN_AUTO_SEED is disabled')
  from steelchain.simulator import generate
  generate(path,seed=20261122,scenario='normal',days=1096)
 return path
ensure_simulated_database(DB)
migrate_and_seed(DB)
app=FastAPI(title='SteelChain Agent API',version='1.0.0')
# `null` is the Origin used by a directly opened file:// HTML workbench.
# Keep the API bound to localhost for local demos; this is not an internet CORS policy.
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3000','http://127.0.0.1:3000','null'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
class TurnRequest(BaseModel):
 message:str=Field(min_length=1,max_length=4000)
 conversation_id:str|None=None
 role:str|None=None
class TurnResponse(BaseModel):
 schema_version:str; conversation_id:str; status:str; role:str|None; intent:str; parameters:dict; results:list[dict]; summary:str; warnings:list[str]; data_origin:str; call_logs:list[dict]
@app.get('/health')
def health(): return {'status':'ok','data_origin':'SIMULATED'}
@app.get('/api/v1/dashboard/price-series')
def price_series(region:str|None=None,category_id:int|None=None,days:int=Query(default=90,ge=7,le=1096)):
 con=sqlite3.connect(DB)
 rows=con.execute('SELECT day,AVG(price) price FROM prices WHERE (? IS NULL OR region=?) AND (? IS NULL OR category_id=?) GROUP BY day ORDER BY day DESC LIMIT ?', (region,region,category_id,category_id,days)).fetchall(); con.close(); rows.reverse()
 try:
  from steelchain.ml.forecast import predict
  forecasts=[predict('y',h) for h in (7,15,30)]
  if any(x.get('data_origin')!='SIMULATED_MODEL_PREDICTION' for x in forecasts): forecasts=[]
 except Exception: forecasts=[]
 return {'history':[{'date':r[0],'value':r[1]} for r in rows],'forecasts':forecasts,'forecast_status':'available' if forecasts else 'model_unavailable','data_origin':'SIMULATED'}
@app.get('/api/v1/dashboard/supply-demand')
def supply_demand(region:str|None=None):
 con=sqlite3.connect(DB)
 rows=con.execute('SELECT c.id,c.name,COALESCE((SELECT SUM(r.quantity) FROM requirements r WHERE r.category_id=c.id AND (? IS NULL OR r.region=?)),0),COALESCE((SELECT SUM(o.quantity) FROM offers o WHERE o.category_id=c.id AND (? IS NULL OR o.region=?)),0) FROM categories c ORDER BY c.id',(region,region,region,region)).fetchall(); con.close()
 return {'items':[{'category_id':r[0],'category':r[1],'demand_ton':r[2],'supply_ton':r[3]} for r in rows],'data_origin':'SIMULATED','basis':'当前模拟采购需求/销售挂牌快照，不是预测'}
@app.get('/api/v1/dashboard/supply-demand-forecasts')
def supply_demand_forecasts():
 try:
  from steelchain.ml.forecast import predict
  forecasts=[predict(target,h) for target in ('demand','supply') for h in (7,15,30)]
  return {'forecasts':forecasts,'forecast_status':'available','data_origin':'SIMULATED_MODEL_PREDICTION','basis':'模型预测的系统日需求量/供应量；训练目标为显式合成序列'}
 except Exception as e:
  return {'forecasts':[],'forecast_status':'model_unavailable','reason':type(e).__name__,'data_origin':'NONE','basis':'模型不可用，不返回预测数字'}
@app.get('/api/v1/dashboard/overview')
def overview():
 con=sqlite3.connect(DB); data={t:con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('parties','offers','requirements','orders')}; con.close(); return {'counts':data,'data_origin':'SIMULATED'}
@app.get('/api/v1/categories/taxonomy')
def taxonomy():
 con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
 groups=con.execute('SELECT id,level1,level2,level3 FROM scrap_taxonomy ORDER BY id').fetchall()
 mappings=con.execute('SELECT c.id,c.name,m.taxonomy_id,m.mapping_status,m.note,t.level2,t.level3 FROM categories c JOIN category_taxonomy_map m ON m.category_id=c.id LEFT JOIN scrap_taxonomy t ON t.id=m.taxonomy_id ORDER BY c.id').fetchall(); con.close()
 return {'items':[dict(r) for r in groups],'legacy_mappings':[dict(r) for r in mappings],'data_origin':'SIMULATED'}
@app.post('/api/v1/assistant/turns',response_model=TurnResponse)
def assistant_turn(req:TurnRequest):
 try: return invoke(req.message,req.conversation_id,req.role).model_dump()
 except ValueError as e: raise HTTPException(status_code=422,detail=str(e))
 except Exception as e: raise HTTPException(status_code=500,detail={'code':'AGENT_RUNTIME_ERROR','message':type(e).__name__})
