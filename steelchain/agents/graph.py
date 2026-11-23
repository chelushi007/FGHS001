from typing import Any, Literal, TypedDict
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from pathlib import Path
from datetime import date
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

def tool_optimize(role):
    # Keep the chat demo party-scoped; otherwise one selected role optimizes the entire market.
    demo_party={'steel_mill':'ST-001','recycler':'RE-001','individual':'IN-011'}.get(role)
    return optimize(role,str(DB),party_id=demo_party,year=2025)
def tool_compliance(role):
    con=sqlite3.connect(DB); r=con.execute("SELECT COUNT(*) FROM parties WHERE role='INDIVIDUAL'").fetchone()[0]; bad=con.execute("SELECT COUNT(*) FROM requirements r JOIN parties p ON p.id=r.party_id WHERE p.role='INDIVIDUAL'").fetchone()[0]; q=con.execute('SELECT COUNT(*) FROM quotas WHERE limit_amount>5000000 OR used_amount+reserved_amount>limit_amount').fetchone()[0]; con.close()
    result={'status':'ok' if bad==0 and q==0 else 'violation','individual_count':r,'individual_purchase_requirements':bad,'quota_violations':q,'individual_allowed_direction':'SELL_ONLY','annual_simulated_quota_limit':5000000,'data_origin':'SIMULATED'}
    if role=='individual':
        con=sqlite3.connect(DB); row=con.execute('SELECT limit_amount,used_amount,reserved_amount FROM quotas WHERE party_id=? AND year=?',('IN-011',2025)).fetchone(); con.close()
        if row:
            result.update({'demo_party_id':'IN-011','quota_year':2025,'quota_used_amount':float(row[1]),'quota_reserved_amount':float(row[2]),'quota_remaining_amount':float(row[0]-row[1]-row[2])})
    return result

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

def _money(value):
    return f"¥{float(value):,.2f}"

def _role_summary(role, intent, outputs):
    by_agent={item.get('agent'):item for item in outputs}
    optimization=by_agent.get('optimization',{})
    if intent=='optimize' and optimization:
        if optimization.get('status') not in ('OPTIMAL','FEASIBLE'):
            return f"{ {'steel_mill':'钢厂采购','recycler':'回收商经营','individual':'自然人销售'}.get(role,'经营') }优化暂未找到可行方案：{optimization.get('explanation','当前约束下无可用交易路径。')}"
        totals=optimization.get('totals') or {}; qty=float(totals.get('quantity_ton') or 0); count=int(optimization.get('trade_count',len(optimization.get('trades') or [])))
        if role=='steel_mill':
            return f"钢厂示例主体 ST-001 采购优化已完成：推荐采购 {qty:,.3f} 吨，预计到厂成本 {_money(totals.get('buyer_landed_cost',0))}，共 {count} 笔交易。成本测算含采购价、运输、加工、质量损耗和资金成本；下方可查看交易明细与约束依据。"
        if role=='recycler':
            seller_net=sum(float(trade.get('seller_net_before_tax') or 0) for trade in optimization.get('trades') or [])
            return f"回收商示例主体 RE-001 经营优化已完成：推荐销售路径涉及 {qty:,.3f} 吨，方案测算销售收入 {_money(totals.get('seller_revenue',0))}，按模型成本项计算的卖方税前净额 {_money(seller_net)}，共 {count} 笔交易。模型目标为在模拟报价和成本约束下筛选购销路径；该净额不等同于财务账面利润。"
        if role=='individual':
            before=float(optimization.get('quota_remaining_before') or 0); used=float(optimization.get('quota_consumption') or 0); after=max(0,before-used)
            seller_net=sum(float(trade.get('seller_net_before_tax') or 0) for trade in optimization.get('trades') or [])
            return f"自然人示例主体 IN-011（2025模拟年度）销售优化已完成：建议销售 {qty:,.3f} 吨，方案测算销售收入 {_money(totals.get('seller_revenue',0))}，扣除模型成本项后的税前净额 {_money(seller_net)}；本次预计占用年度模拟额度 {_money(used)}，方案后的可用额度约 {_money(after)}。额度以台账为准；方案仅包含销售路径，仍需成交前复核。"
    if intent=='forecast':
        pricing=(by_agent.get('pricing') or {}).get('forecast') or {}
        supply=by_agent.get('supply_demand') or {}; demand=supply.get('demand') or {}; availability=supply.get('supply') or {}
        target_date=pricing.get('target_date')
        if target_date and target_date < date.today().isoformat():
            role_name={'steel_mill':'钢厂采购','recycler':'回收商经营','individual':'自然人销售'}.get(role,'经营')
            return f"{role_name}暂不输出预测建议：本地模型记录的目标日为 {target_date}，早于当前日期，不能作为未来预测使用。预测与供需模块的角色指标、刷新频率及区域/品类口径尚未完成设计。"
        if pricing.get('data_origin')!='SIMULATED_MODEL_PREDICTION':
            return '预测模型或所需数据暂不可用，本次不返回预测数值。请检查模型制品和预测数据。'
        horizon=pricing.get('horizon_days'); price=pricing.get('predicted_value'); unit='元/吨'
        context=[]
        if demand.get('data_origin')=='SIMULATED_MODEL_PREDICTION' and demand.get('predicted_value') is not None: context.append(f"系统日需求预测 {float(demand['predicted_value']):,.2f} 吨")
        if availability.get('data_origin')=='SIMULATED_MODEL_PREDICTION' and availability.get('predicted_value') is not None: context.append(f"系统日供应预测 {float(availability['predicted_value']):,.2f} 吨")
        context_text=('；'+'；'.join(context)) if context else ''
        if role=='steel_mill':
            return f"钢厂采购参考：未来 {horizon} 天模拟模型价格预测为 {float(price):,.2f} {unit}（目标日 {pricing.get('target_date')}）{context_text}。模型：{pricing.get('model')}。"
        if role=='recycler':
            return f"回收商经营参考：未来 {horizon} 天模拟模型销售行情预测为 {float(price):,.2f} {unit}（目标日 {pricing.get('target_date')}）{context_text}。模型：{pricing.get('model')}。"
        if role=='individual':
            return f"自然人销售参考：未来 {horizon} 天模拟模型价格预测为 {float(price):,.2f} {unit}（目标日 {pricing.get('target_date')}）。自然人仅可销售；实际可售数量与额度须按本人库存、资格和台账核验。模型：{pricing.get('model')}。"
    compliance=by_agent.get('compliance')
    if intent=='compliance' and compliance:
        people=int(compliance.get('individual_count',0)); bad=int(compliance.get('individual_purchase_requirements',0)); violations=int(compliance.get('quota_violations',0)); limit=_money(compliance.get('annual_simulated_quota_limit',5_000_000))
        if role=='individual':
            if compliance.get('demo_party_id'):
                return f"自然人示例主体 {compliance['demo_party_id']} 合规核验：自然人只允许销售，{compliance.get('quota_year')} 年度反向开票模拟额度上限为 {limit}，已用 {_money(compliance.get('quota_used_amount',0))}，预留 {_money(compliance.get('quota_reserved_amount',0))}，可用 {_money(compliance.get('quota_remaining_amount',0))}。另对全库样本检查到 {bad} 条自然人采购需求、{violations} 项额度超限。"
            return f"自然人合规核验：自然人只允许销售，年度反向开票模拟额度上限为 {limit}。当前模拟库检查到 {bad} 条自然人采购需求、{violations} 项额度超限；这是一项系统级样本检查，不代表个人实时剩余额度。"
        if role=='steel_mill':
            return f"钢厂合规核验：钢厂可采购和销售废钢。系统级模拟检查覆盖 {people} 位自然人，发现 {bad} 条自然人采购需求、{violations} 项额度超限。钢厂具体交易仍须逐笔校验库存、质量、物流和订单状态。"
        if role=='recycler':
            return f"回收商合规核验：回收商可采购和销售废钢。系统级模拟检查覆盖 {people} 位自然人，发现 {bad} 条自然人采购需求、{violations} 项额度超限。回收商具体交易仍须逐笔校验供需、库存、质量和物流。"
    match=by_agent.get('matching')
    if intent=='matching' and match:
        count=int(match.get('candidate_count',0))
        label={'steel_mill':'钢厂采购','recycler':'回收商购销','individual':'自然人销售'}.get(role,'供需')
        return f"{label}初筛得到 {count} 条报价与需求候选。候选仅按当前品类、报价和数量做初筛，不等于可成交路径；仍需成交前校验库存、质量、物流、资格和额度。"
    label={'steel_mill':'钢厂采购与原料经营','recycler':'回收商购销与利润管理','individual':'自然人废钢销售与额度合规'}.get(role,'废钢经营')
    return f"{label}助手已就绪，可提供角色对应的经营优化和合规核验。预测与供需模块的业务口径尚未完成设计；请提出采购、销售、利润或额度问题。所有业务数值均由后端业务规则或优化器计算。"

def _has_expired_prediction(value):
    if isinstance(value,dict):
        target=value.get('target_date')
        if value.get('data_origin')=='SIMULATED_MODEL_PREDICTION' and target and target < date.today().isoformat(): return True
        return any(_has_expired_prediction(item) for item in value.values())
    if isinstance(value,list): return any(_has_expired_prediction(item) for item in value)
    return False

def _hide_expired_prediction_values(value):
    if isinstance(value,dict):
        result={key:_hide_expired_prediction_values(item) for key,item in value.items()}
        target=value.get('target_date')
        if value.get('data_origin')=='SIMULATED_MODEL_PREDICTION' and target and target < date.today().isoformat():
            result['predicted_value']=None; result['status']='stale'; result['stale']=True
        return result
    if isinstance(value,list): return [_hide_expired_prediction_values(item) for item in value]
    return value

def _bounded_outputs(outputs, trade_limit=10):
    public=[]
    for item in outputs:
        if item.get('agent')=='optimization' and isinstance(item.get('trades'),list):
            item=dict(item); trades=item['trades']; item['trade_count']=int(item.get('trade_count',len(trades))); item['trades']=trades[:trade_limit]; item['trades_truncated']=len(trades)>trade_limit
        public.append(item)
    return public

def invoke(message,conversation_id=None,role=None):
    cid=conversation_id or str(uuid.uuid4()); prior=_CONTEXT.get(cid,{}); effective_role=role or prior.get('role')
    state=_GRAPH.invoke({'message':message,'conversation_id':cid,'role':effective_role},{'configurable':{'thread_id':cid}})
    outputs=state.get('outputs',[]); statuses=[o.get('status') for o in outputs]
    missing=any(_has_missing(o) for o in outputs)
    expired_prediction=state['intent']=='forecast' and _has_expired_prediction(outputs)
    status='needs_data' if missing and all(_has_missing(o) for o in outputs) else ('partial' if missing else 'ok')
    warnings=[]
    if missing: warnings.append('部分能力缺少可用预测模型或业务数据；没有生成缺失数值。')
    if expired_prediction:
        status='needs_data' if not missing else 'partial'
        warnings.append('模型记录的预测目标日早于当前日期；本次不将过期预测作为未来经营建议。')
    if any('SIMULATED_MODEL_PREDICTION' in str(o) for o in outputs): warnings.append('预测来自模拟数据模型/基线，不能代表真实市场结果。')
    summary=_role_summary(state.get('role'),state['intent'],outputs) if outputs else '未能形成可执行计划。'
    origin='SIMULATED_MODEL_PREDICTION' if any('SIMULATED_MODEL_PREDICTION' in str(o) for o in outputs) else ('MIXED' if any(_has_missing(o) for o in outputs) and outputs else ('SIMULATED' if outputs else 'NONE'))
    _CONTEXT[cid]={'role':state.get('role') or effective_role,'last_intent':state['intent']}
    visible_outputs=_bounded_outputs(outputs)
    if expired_prediction: visible_outputs=_hide_expired_prediction_values(visible_outputs)
    return AgentOutput(conversation_id=cid,status=status,role=state.get('role'),intent=state['intent'],parameters=state['parameters'],results=visible_outputs,summary=summary,warnings=warnings,data_origin=origin,call_logs=state.get('logs',[]))
