from dataclasses import dataclass, asdict
from datetime import date
import sqlite3
from pathlib import Path
from ortools.linear_solver import pywraplp

ROLES={"steel_mill":"STEEL_MILL","recycler":"RECYCLER","individual":"INDIVIDUAL"}

@dataclass(frozen=True)
class CostConfig:
    transport_per_ton_region_step: float=18.0
    processing_per_ton: float=35.0
    quality_loss_rate: float=0.02
    annual_capital_rate: float=0.08
    capital_days: int=30
    individual_quota_limit: float=5_000_000.0

def cost_breakdown(unit_price, region_steps, cfg):
    transport=region_steps*cfg.transport_per_ton_region_step
    processing=cfg.processing_per_ton
    quality_loss=unit_price*cfg.quality_loss_rate
    capital=unit_price*cfg.annual_capital_rate*cfg.capital_days/365
    return {"purchase_price":unit_price,"transport":transport,"processing":processing,"quality_loss":quality_loss,"capital":capital,"total":unit_price+transport+processing+quality_loss+capital}

def _region_distance(a,b):
    order=["华北","东北","华东","华中","华南","西南"]
    return min(abs(order.index(a)-order.index(b)),len(order)-abs(order.index(a)-order.index(b))) if a in order and b in order else (0 if a==b else 3)

def optimize(role, db_path, party_id=None, year=None, cfg=None, transport_capacity_ton=100000):
    if role not in ROLES: raise ValueError('role must be steel_mill, recycler, or individual')
    cfg=cfg or CostConfig(); year=year or date.today().year
    con=sqlite3.connect(db_path); con.row_factory=sqlite3.Row
    role_code=ROLES[role]
    if role == "steel_mill":
        sellers=con.execute("SELECT o.*,p.role seller_role,p.region seller_region,i.quantity inventory_qty,i.reserved FROM offers o JOIN parties p ON p.id=o.party_id JOIN inventory i ON i.id=o.inventory_id WHERE (? IS NULL OR p.id<>?) ORDER BY o.id",(party_id,party_id)).fetchall()
        buyers=con.execute("SELECT r.*,p.role buyer_role,p.region buyer_region FROM requirements r JOIN parties p ON p.id=r.party_id WHERE p.role='STEEL_MILL' AND (? IS NULL OR p.id=?) ORDER BY r.id",(party_id,party_id)).fetchall()
    else:
        sellers=con.execute("SELECT o.*,p.role seller_role,p.region seller_region,i.quantity inventory_qty,i.reserved FROM offers o JOIN parties p ON p.id=o.party_id JOIN inventory i ON i.id=o.inventory_id WHERE p.role=? AND (? IS NULL OR p.id=?) ORDER BY o.id",(role_code,party_id,party_id)).fetchall()
        buyers=con.execute("SELECT r.*,p.role buyer_role,p.region buyer_region FROM requirements r JOIN parties p ON p.id=r.party_id WHERE p.role IN ('STEEL_MILL','RECYCLER') AND (? IS NULL OR p.id<>?) ORDER BY r.id",(party_id,party_id)).fetchall()
    quota_remaining=cfg.individual_quota_limit
    if role=='individual' and party_id:
        q=con.execute('SELECT limit_amount-used_amount-reserved_amount rem FROM quotas WHERE party_id=? AND year=?',(party_id,year)).fetchone()
        quota_remaining=max(0,float(q['rem'])) if q else cfg.individual_quota_limit
    con.close()
    # Variables are integer kilograms for deterministic integral allocation.
    solver=pywraplp.Solver.CreateSolver('SCIP') or pywraplp.Solver.CreateSolver('CBC')
    if solver is None: raise RuntimeError('OR-Tools SCIP/CBC mixed-integer solver unavailable')
    arcs=[]
    for offer in sellers:
        available=max(0,float(offer['quantity'])-float(offer['reserved']))
        if available<=0: continue
        for req in buyers:
            if offer['category_id']!=req['category_id'] or offer['party_id']==req['party_id']: continue
            if float(req['max_price']) < float(offer['price']): continue
            steps=_region_distance(offer['region'],req['region'])
            breakdown=cost_breakdown(float(offer['price']),steps,cfg)
            # Reject buyers whose full landed cost exceeds their stated ceiling.
            if role=='steel_mill' and breakdown['total']>float(req['max_price']): continue
            cap=min(available,float(req['quantity']),transport_capacity_ton)
            var=solver.IntVar(0,int(cap*1000),f"x_{offer['id']}_{req['id']}")
            arcs.append((offer,req,var,steps,breakdown))
    if not arcs:
        return {"status":"INFEASIBLE","role":role,"trades":[],"explanation":"没有同时满足品类、报价、需求和可用库存的交易路径。","data_origin":"SIMULATED"}
    for offer in sellers:
        vars_=[a[2] for a in arcs if a[0]['id']==offer['id']]
        if vars_: solver.Add(solver.Sum(vars_)<=int(max(0,float(offer['quantity'])-float(offer['reserved']))*1000))
    for req in buyers:
        vars_=[a[2] for a in arcs if a[1]['id']==req['id']]
        if vars_: solver.Add(solver.Sum(vars_)<=int(float(req['quantity'])*1000))
    solver.Add(solver.Sum(a[2] for a in arcs)<=int(transport_capacity_ton*1000))
    if role=='individual':
        solver.Add(solver.Sum(a[2]*float(a[0]['price'])/1000 for a in arcs)<=quota_remaining)
    objective=solver.Objective()
    for offer,req,var,steps,cost in arcs:
        price=float(offer['price']); buyer_cap=float(req['max_price'])
        if role=='steel_mill': coefficient=-(cost['total']) # fixed fill objective is added as deterministic tie-break below
        elif role=='recycler': coefficient=buyer_cap-cost['total']
        else: coefficient=price-cost['transport']-cost['processing']-cost['quality_loss']-cost['capital']
        # tiny positive trade preference for steel mills while preserving cost priority
        if role=='steel_mill': coefficient=100000-cost['total']
        objective.SetCoefficient(var,coefficient/1000)
    objective.SetMaximization()
    solver.SetTimeLimit(10000); status=solver.Solve()
    if status not in (pywraplp.Solver.OPTIMAL,pywraplp.Solver.FEASIBLE):
        return {"status":"INFEASIBLE","role":role,"trades":[],"explanation":"在库存、需求、报价、物流或额度约束下无可行方案。","data_origin":"SIMULATED"}
    trades=[]; total_qty=total_cost=total_revenue=0.0
    for offer,req,var,steps,cost in arcs:
        qty=var.solution_value()/1000
        if qty<=0: continue
        recommended_price=round(min(float(req['max_price']),float(offer['price'])+cost['total']-float(offer['price'])),2)
        landed=cost['total']; revenue=recommended_price*qty; costs=landed*qty
        item={"seller_id":offer['party_id'],"buyer_id":req['party_id'],"offer_id":offer['id'],"requirement_id":req['id'],"category_id":offer['category_id'],"quantity_ton":qty,"recommended_price_per_ton":recommended_price,"buyer_max_price_per_ton":float(req['max_price']),"unit_cost":cost,"distance_steps":steps,"transport_capacity_ton":qty,"seller_role":offer['seller_role'],"buyer_role":req['buyer_role'],"seller_revenue":revenue,"buyer_landed_cost":costs,"seller_net_before_tax":(float(offer['price'])-cost['transport']-cost['processing']-cost['quality_loss']-cost['capital'])*qty,"constraints":["品类匹配","供需数量上限","库存可用量","报价不高于买方上限","物流容量",*( ["自然人年度模拟额度"] if role=='individual' else [])]}
        trades.append(item); total_qty+=qty; total_cost+=costs; total_revenue+=revenue
    return {"status":"OPTIMAL" if status==pywraplp.Solver.OPTIMAL else "FEASIBLE","role":role,"objective":"采购成本最小化" if role=='steel_mill' else ("经营利润最大化" if role=='recycler' else "销售净收益最大化"),"trades":trades,"totals":{"quantity_ton":total_qty,"buyer_landed_cost":total_cost,"seller_revenue":total_revenue,"net_value":total_revenue-total_cost},"quota_remaining_before":quota_remaining if role=='individual' else None,"quota_consumption":sum(t['quantity_ton']*t['recommended_price_per_ton'] for t in trades) if role=='individual' else None,"data_origin":"SIMULATED","solver":"OR-Tools SCIP/CBC","explanation":"在给定成本参数及约束下由混合整数优化求解；建议价格不超过需求最高价。"}
