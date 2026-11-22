'use client';
import ReactECharts from 'echarts-for-react';
import {useEffect,useMemo,useState} from 'react';

type Point={date:string;value:number};
type Forecast={target:string;horizon_days:number;target_date:string;predicted_value:number;model:string;model_version:string;data_origin:string};
type SupplyForecast={target:'demand'|'supply';horizon_days:number;predicted_value:number;model_version:string;data_origin:string};
type Category={category_id:number;category:string;demand_ton:number;supply_ton:number};
const API=process.env.NEXT_PUBLIC_API_BASE||'http://localhost:8000';
export function PriceChart(){
 const [data,setData]=useState<{history:Point[];forecasts:Forecast[];forecast_status:string}|null>(null);
 useEffect(()=>{fetch(`${API}/api/v1/dashboard/price-series?days=90`).then(r=>{if(!r.ok)throw new Error();return r.json()}).then(setData).catch(()=>setData(null))},[]);
 const option=useMemo(()=>{
  const forecasts=(data?.forecasts||[]).filter(x=>x.data_origin==='SIMULATED_MODEL_PREDICTION'&&Number.isFinite(x.predicted_value));
  const dates=[...new Set([...(data?.history||[]).map(x=>x.date),...forecasts.map(x=>x.target_date)])].sort();
  const series:any[]=[{name:'模拟历史均价',type:'line',smooth:true,symbol:'none',connectNulls:false,data:dates.map(day=>data?.history.find(x=>x.date===day)?.value??null),lineStyle:{color:'#1e6b55',width:2.5},areaStyle:{color:'rgba(30,107,85,.08)'}}];
  const colors=['#4b76bb','#bd8d48','#8067aa'];
  forecasts.forEach((forecast,index)=>series.push({name:`${forecast.horizon_days}天${forecast.model}预测`,type:'scatter',symbolSize:10,data:dates.map(day=>day===forecast.target_date?forecast.predicted_value:null),itemStyle:{color:colors[index%colors.length]},emphasis:{scale:true},tooltip:{formatter:`${forecast.target_date}<br/>${forecast.horizon_days}天预测: ${forecast.predicted_value.toLocaleString(undefined,{maximumFractionDigits:2})}<br/>${forecast.model_version}<br/>模拟模型预测`}}));
  return {tooltip:{trigger:'axis'},legend:{show:forecasts.length>0,bottom:0,textStyle:{color:'#738096',fontSize:9}},grid:{left:42,right:20,top:18,bottom:forecasts.length?42:25},xAxis:{type:'category',data:dates.map(x=>x.slice(5)),axisLabel:{color:'#738096'}},yAxis:{type:'value',axisLabel:{color:'#738096'},splitLine:{lineStyle:{color:'#edf0f4'}}},series};
 },[data]);
 return <div className="chart-wrap"><div className="chart-head"><div><span className="eyebrow">价格趋势</span><h3>区域废钢行情</h3></div><span className="badge sim">模拟数据</span></div><div className="chart-legend"><span className="dot green"/>90日历史均价<span className="forecast-note">{data?.forecast_status==='model_unavailable'?'预测模型暂不可用':data?.forecast_status==='available'?'7/15/30天模拟模型预测已加载':''}</span></div><ReactECharts option={option} style={{height:250}} notMerge /></div>
}
export function SupplyChart(){
 const [items,setItems]=useState<Category[]>([]);
 useEffect(()=>{fetch(`${API}/api/v1/dashboard/supply-demand`).then(r=>r.json()).then(x=>setItems(x.items||[])).catch(()=>setItems([]))},[]);
 const option=useMemo(()=>({tooltip:{trigger:'axis'},legend:{bottom:0,textStyle:{color:'#738096'}},grid:{left:42,right:18,top:18,bottom:42},xAxis:{type:'category',data:items.slice(0,8).map(x=>x.category),axisLabel:{color:'#738096',rotate:20}},yAxis:{type:'value',axisLabel:{color:'#738096'},splitLine:{lineStyle:{color:'#edf0f4'}}},series:[{name:'需求挂牌',type:'bar',data:items.slice(0,8).map(x=>x.demand_ton),itemStyle:{color:'#3756a6',borderRadius:[4,4,0,0]}},{name:'供应挂牌',type:'bar',data:items.slice(0,8).map(x=>x.supply_ton),itemStyle:{color:'#7db9a6',borderRadius:[4,4,0,0]}}]}),[items]);
 return <div className="chart-wrap"><div className="chart-head"><div><span className="eyebrow">供需结构</span><h3>品类需求与供给</h3></div><span className="badge sim">模拟快照</span></div><div className="chart-legend">当前采购需求与销售挂牌对比，不代表未来预测</div><ReactECharts option={option} style={{height:250}} notMerge /></div>
}
export function SupplyForecastChart(){
 const [data,setData]=useState<{forecasts:SupplyForecast[];forecast_status:string}|null>(null);
 useEffect(()=>{fetch(`${API}/api/v1/dashboard/supply-demand-forecasts`).then(r=>{if(!r.ok)throw new Error();return r.json()}).then(setData).catch(()=>setData({forecasts:[],forecast_status:'model_unavailable'}))},[]);
 const option=useMemo(()=>({tooltip:{trigger:'axis'},legend:{bottom:0,textStyle:{color:'#738096'}},grid:{left:45,right:18,top:20,bottom:38},xAxis:{type:'category',data:[7,15,30].map(x=>`${x}天`),axisLabel:{color:'#738096'}},yAxis:{type:'value',name:'吨/日',axisLabel:{color:'#738096'},splitLine:{lineStyle:{color:'#edf0f4'}}},series:(['demand','supply'] as const).map((target,index)=>({name:target==='demand'?'需求模型预测':'供应模型预测',type:'line',smooth:true,symbol:'circle',symbolSize:7,data:[7,15,30].map(h=>data?.forecasts.find(x=>x.target===target&&x.horizon_days===h)?.predicted_value??null),lineStyle:{color:index?'#7db9a6':'#3756a6',width:2},itemStyle:{color:index?'#7db9a6':'#3756a6'}}))}),[data]);
 return <div className="chart-wrap"><div className="chart-head"><div><span className="eyebrow">供需预测</span><h3>系统日需求与供应量</h3></div><span className="badge sim">模拟模型预测</span></div><div className="chart-legend">{data?.forecast_status==='available'?<>单位：吨/日 · 目标序列由静态挂牌及模拟趋势构造<span className="forecast-note">{[...new Set(data.forecasts.map(x=>x.model_version))].join(' / ')}</span></>:'预测模型暂不可用，不显示预测数值'}</div><ReactECharts option={option} style={{height:215}} notMerge /><p className="footnote">来源：模拟训练数据与已版本化的模型预测；需求/供应目标为合成序列，不能代表真实市场业务。</p></div>
}
