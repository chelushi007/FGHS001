from typing import Any, Literal, TypedDict
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from pathlib import Path
import re, sqlite3, time, uuid, os
from steelchain.optimization.planner import optimize

DB=Path(os.environ.get('STEELCHAIN_DB',Path(__file__).resolve().parents[2]/'data'/'steelchain.sqlite'))

class AgentOutput(BaseModel):
    schema_version: Literal['1.0']='1.0'
    conversation_id: str
    status: Literal['ok','partial','needs_data','error']
    role: str|None=None
    intent: str
    parameters: dict[str,Any]=Field(default_factory=dict)
    results: list[dict[str,Any]]=Field(default_factory=list)
    summary: str
    warnings: list[str]=Field(default_factory=list)
    data_origin: Literal['SIMULATED','SIMULATED_MODEL_PREDICTION','MIXED','NONE']='NONE'
    call_logs: list[dict[str,Any]]=Field(default_factory=list)

class State(TypedDict,total=False):
    conversation_id:str; message:str; role:str|None; intent:str; parameters:dict; plan:list[str]; outputs:list[dict]; logs:list[dict]; warnings:list[str]; status:str

def identify(message, context=None):
    text=message.lower(); role=(context or {}).get('role')
    if any(w in text for w in ('自然人','个人卖','个人销售')): role='individual'
    elif any(w in text for w in ('钢厂','钢铁厂')): role='steel_mill'
    elif any(w in text for w in ('回收商','回收企业')): role='recycler'
    if any(w in text for w in ('预测','行情','价格走势')): intent='forecast'
    elif any(w in text for w in ('合规','额度','资格','风控')): intent='compliance'
    elif any(w in text for w in ('优化','利润','收益','成本')): intent='optimize'
    elif any(w in text for w in ('匹配','交易','采购','销售','供需')): intent='matching'
    else: intent='general'
    h=re.search(r'\b(7|15|30)\s*天',text); cat=re.search(r'品类\s*[:：]?\s*(\d+)',message); region=next((r for r in ('华北','华东','华南','华中','西南','东北') if r in message),None)
    return role,intent,{'horizon_days':int(h.group(1)) if h else 7,'category_id':int(cat.group(1)) if cat else None,'region':region}

def tool_market(query):
    con=sqlite3.connect(DB); row=con.execute('SELECT AVG(price),MAX(day) FROM prices WHERE (? IS NULL OR region=?) AND (? IS NULL OR category_id=?)',(query.get('region'),query.get('region'),query.get('category_id'),query.get('category_id'))).fetchone(); con.close()
    if not row or row[0] is None: return {'status':'missing_data','reason':'没有匹配行情记录','data_origin':'SIMULATED'}
    return {'status':'ok','historical_average':row[0],'through_date':row[1],'data_origin':'SIMULATED','note':'历史模拟行情统计，不是预测价格'}

def tool_forecast(target,horizon):
    try:
        from steelchain.ml.forecast import predict
        return predict(target,horizon)
    except Exception as exc:
        return {'status':'missing_data','target':target,'horizon_days':horizon,'reason':f'预测模型不可用：{type(exc).__name__}','data_origin':'NONE'}

def tool_matching():
    con=sqlite3.connect(DB); rows=con.execute("SELECT o.id,r.id,o.party_id,r.party_id,o.category_id,MIN(o.quantity,r.quantity),o.price,r.max_price FROM offers o JOIN requirements r ON r.category_id=o.category_id AND r.party_id<>o.party_id WHERE o.price<=r.max_price ORDER BY o.id LIMIT 20").fetchall(); con.close()
    return {'status':'ok' if rows else 'missing_data','candidate_count':len(rows),'candidates':[{'offer_id':x[0],'requirement_id':x[1],'seller_id':x[2],'buyer_id':x[3],'category_id':x[4],'quantity_ton':x[5],'offer_price':x[6],'buyer_max_price':x[7]} for x in rows],'data_origin':'SIMULATED'}

def tool_optimize(role): return optimize(role,str(DB))
def tool_compliance(role):
    con=sqlite3.connect(DB); r=con.execute("SELECT COUNT(*) FROM parties WHERE role='INDIVIDUAL'").fetchone()[0]; bad=con.execute("SELECT COUNT(*) FROM requirements r JOIN parties p ON p.id=r.party_id WHERE p.role='INDIVIDUAL'").fetchone()[0]; q=con.execute('SELECT COUNT(*) FROM quotas WHERE limit_amount>5000000 OR used_amount+reserved_amount>limit_amount').fetchone()[0]; con.close()
    return {'status':'ok' if bad==0 and q==0 else 'violation','individual_count':r,'individual_purchase_requirements':bad,'quota_violations':q,'individual_allowed_direction':'SELL_ONLY','annual_simulated_quota_limit':5000000,'data_origin':'SIMULATED'}

class GraphState(State): pass

def build_graph():
    g=StateGraph(GraphState)
    def classify(s):
        role,intent,params=identify(s['message'],{'role':s.get('role')}); plan=[]
        if intent=='forecast': plan=['supply_demand','pricing']
        elif intent=='matching': plan=['matching']
        elif intent=='optimize': plan=['optimization']
        elif intent=='compliance': plan=['compliance']
        else: plan=['compliance']
        return {'role':role,'intent':intent,'parameters':params,'plan':plan,'outputs':[],'logs':[],'warnings':[],'status':'ok'}
    def specialist(name,fn):
        def run(s):
            started=time.time(); output=fn(s)
            return {'outputs':s.get('outputs',[])+[{'agent':name,**output}], 'logs':s.get('logs',[])+[{'agent':name,'tool':name,'duration_ms':round((time.time()-started)*1000,2),'status':output.get('status','ok')}]}
        return run
    g.add_node('classify',classify)
    g.add_node('supply_demand',specialist('supply_demand',lambda s:{'demand':tool_forecast('demand',s['parameters']['horizon_days']),'supply':tool_forecast('supply',s['parameters']['horizon_days'])}))
    g.add_node('pricing',specialist('pricing',lambda s:{'forecast':tool_forecast('y',s['parameters']['horizon_days']),'market_context':tool_market(s['parameters'])}))
    g.add_node('matching',specialist('matching',lambda s:tool_matching()))
    g.add_node('optimization',specialist('optimization',lambda s:tool_optimize(s['role']) if s.get('role') else {'status':'missing_data','reason':'请说明主体角色','data_origin':'NONE'}))
    g.add_node('compliance',specialist('compliance',lambda s:tool_compliance(s['role'])))
    g.add_node('summarize',lambda s:{'status':'partial' if any('missing_data' in str(o) for o in s['outputs']) else s['status']})
    g.add_edge(START,'classify')
    def route(s): return s['plan'][0] if s.get('plan') else 'summarize'
    g.add_conditional_edges('classify',route,{n:n for n in ('supply_demand','pricing','matching','optimization','compliance')}|{'summarize':'summarize'})
    def next_node(s):
        completed=[x['agent'] for x in s.get('outputs',[])]
        todo=[n for n in s.get('plan',[]) if n not in completed]
        return todo[0] if todo else 'summarize'
    for n in ('supply_demand','pricing','matching','optimization','compliance'):
        g.add_conditional_edges(n,next_node,{x:x for x in ('supply_demand','pricing','matching','optimization','compliance')}|{'summarize':'summarize'})
    g.add_edge('summarize',END)
    return g.compile(checkpointer=MemorySaver())

_GRAPH=build_graph()
_CONTEXT={}
def _has_missing(value):
    if isinstance(value,dict): return value.get('status')=='missing_data' or any(_has_missing(v) for v in value.values())
    if isinstance(value,list): return any(_has_missing(v) for v in value)
    return False
def invoke(message,conversation_id=None,role=None):
    cid=conversation_id or str(uuid.uuid4()); prior=_CONTEXT.get(cid,{}); effective_role=role or prior.get('role')
    state=_GRAPH.invoke({'message':message,'conversation_id':cid,'role':effective_role},{'configurable':{'thread_id':cid}})
    outputs=state.get('outputs',[]); statuses=[o.get('status') for o in outputs]
    missing=any(_has_missing(o) for o in outputs)
    status='needs_data' if missing and all(_has_missing(o) for o in outputs) else ('partial' if missing else 'ok')
    warnings=[]
    if missing: warnings.append('部分能力缺少可用预测模型或业务数据；没有生成缺失数值。')
    if any('SIMULATED_MODEL_PREDICTION' in str(o) for o in outputs): warnings.append('预测来自模拟数据模型/基线，不能代表真实市场结果。')
    summary='已调用后端工具并汇总结构化结果。' if outputs else '未能形成可执行计划。'
    origin='SIMULATED_MODEL_PREDICTION' if any('SIMULATED_MODEL_PREDICTION' in str(o) for o in outputs) else ('MIXED' if any(_has_missing(o) for o in outputs) and outputs else ('SIMULATED' if outputs else 'NONE'))
    _CONTEXT[cid]={'role':state.get('role') or effective_role,'last_intent':state['intent']}
    return AgentOutput(conversation_id=cid,status=status,role=state.get('role'),intent=state['intent'],parameters=state['parameters'],results=outputs,summary=summary,warnings=warnings,data_origin=origin,call_logs=state.get('logs',[]))
