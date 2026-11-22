import json, sqlite3, hashlib, os
from importlib.metadata import version as package_version, PackageNotFoundError
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT=Path(__file__).resolve().parents[2]
DB=Path(os.environ.get('STEELCHAIN_DB',ROOT/'data/steelchain.sqlite')); OUT=Path(os.environ.get('STEELCHAIN_MODEL_DIR',ROOT/'artifacts/models')); REPORT=Path(os.environ.get('STEELCHAIN_MODEL_REPORT',ROOT/'reports/P2_MODEL_EVALUATION.json'))
HORIZONS=(7,15,30); SEED=20261122; DATA_VERSION='P1-sim-v1-seed-20261122-normal'
FEATURES=['day_of_year','day_of_week','month','trend','lag_1','lag_7','lag_14','lag_30','mean_7','mean_30']
FEATURE_VERSION='daily-lag-calendar-v1'
MODEL_VERSION='steelchain-tabular-forecast-v1.0.0'

def load_series():
    con=sqlite3.connect(DB)
    prices=pd.read_sql_query('SELECT day, AVG(price) AS y FROM prices GROUP BY day ORDER BY day',con)
    # P1 has static listings. Build explicit synthetic daily quantities from observed snapshot totals
    # and deterministic calendar modulation. This is a simulated target process, not recorded history.
    demand=pd.read_sql_query('SELECT SUM(quantity) y FROM requirements',con).iloc[0,0]
    supply=pd.read_sql_query('SELECT SUM(quantity) y FROM offers',con).iloc[0,0]
    con.close()
    dates=pd.to_datetime(prices.day)
    t=np.arange(len(prices)); seasonal=np.sin(2*np.pi*t/365.25); weekly=np.sin(2*np.pi*t/7)
    prices['demand']=demand/len(t)*(1+.12*seasonal+.035*weekly+0.00008*t)
    prices['supply']=supply/len(t)*(1+.09*np.sin(2*np.pi*(t+45)/365.25)+.025*weekly-0.000025*t)
    prices['date']=dates
    return prices

def features(frame,target,h):
    d=frame.copy(); d['y']=d[target]
    for lag in [1,7,14,30]: d[f'lag_{lag}']=d.y.shift(lag)
    d['mean_7']=d.y.shift(1).rolling(7).mean(); d['mean_30']=d.y.shift(1).rolling(30).mean()
    d['target']=d.y.shift(-h); d['target_date']=d.date.shift(-h)
    d['day_of_year']=d.date.dt.day_of_year; d['day_of_week']=d.date.dt.day_of_week; d['month']=d.date.dt.month
    d['trend']=np.arange(len(d))/len(d)
    return d.dropna().reset_index(drop=True)

def metrics(y,p):
    y=np.asarray(y); p=np.asarray(p)
    return {'mae':float(mean_absolute_error(y,p)),'rmse':float(np.sqrt(mean_squared_error(y,p))),'mape_pct':float(np.mean(np.abs((y-p)/np.maximum(np.abs(y),1e-8)))*100)}

def make_model(kind):
    if kind=='lightgbm':
        try:
            from lightgbm import LGBMRegressor
        except Exception as exc:
            raise RuntimeError(f'LightGBM unavailable: {type(exc).__name__}') from exc
        return LGBMRegressor(n_estimators=120,max_depth=4,num_leaves=15,learning_rate=.04,verbosity=-1,random_state=SEED,n_jobs=2)
    if kind=='xgboost': return XGBRegressor(n_estimators=120,max_depth=4,learning_rate=.04,subsample=.9,colsample_bytree=.9,objective='reg:squarederror',random_state=SEED,n_jobs=2)
    raise ValueError(kind)

def available_algorithms():
    available=['xgboost']; unavailable={}
    if os.environ.get('STEELCHAIN_ENABLE_LIGHTGBM','auto').lower() in ('0','false','no'):
        unavailable['lightgbm']='disabled_by_configuration'
        return available,unavailable
    try:
        from lightgbm import LGBMRegressor  # noqa: F401
        available.insert(0,'lightgbm')
    except Exception as exc:
        unavailable['lightgbm']=type(exc).__name__
    return available,unavailable

def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def _source_fingerprint(path):
    con=sqlite3.connect(path); source=[]
    for table in ('offers','prices','requirements'):
        columns=[row[1] for row in con.execute(f'PRAGMA table_info({table})')]
        rows=con.execute(f'SELECT * FROM {table} ORDER BY '+','.join(f'"{name}"' for name in columns)).fetchall()
        source.append((table,columns,rows))
    con.close()
    return hashlib.sha256(json.dumps(source,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()

def _version(name):
    try: return package_version(name)
    except PackageNotFoundError: return None

def train():
    OUT.mkdir(parents=True,exist_ok=True); frame=load_series(); results=[]; model_index={}
    n=len(frame); train_end=int(n*.65); val_end=int(n*.80); available,unavailable=available_algorithms()
    train_cutoff=frame.date.iloc[train_end]; validation_cutoff=frame.date.iloc[val_end]
    for target in ('y','demand','supply'):
        source='y' if target=='y' else target
        for h in HORIZONS:
            ds=features(frame,source,h)
            tr=ds[ds.target_date < train_cutoff]
            va=ds[(ds.target_date >= train_cutoff) & (ds.target_date < validation_cutoff)]
            te=ds[ds.target_date >= validation_cutoff]
            if tr.empty or va.empty or te.empty:
                raise RuntimeError(f'insufficient chronological split for {target}/{h}')
            Xtr=tr[FEATURES]; Xva=va[FEATURES]; Xte=te[FEATURES]
            val_baselines={
              'persistence_baseline':metrics(va.target,va.lag_1),
              'moving_average_7_baseline':metrics(va.target,va.mean_7),
            }
            baselines={
              'persistence':metrics(te.target,te.lag_1),
              'moving_average_7':metrics(te.target,te.mean_7),
            }
            candidates=[(val_baselines['persistence_baseline']['mae'],'persistence_baseline'),(val_baselines['moving_average_7_baseline']['mae'],'moving_average_7_baseline')]
            for kind in available:
                mdl=make_model(kind); mdl.fit(Xtr,tr.target)
                val_metrics=metrics(va.target,mdl.predict(Xva))
                test_metrics=metrics(te.target,mdl.predict(Xte))
                # Three sequential rolling-origin evaluation windows, with no future rows in each fit.
                roll=[]
                for frac in (.80,.87,.93):
                    origin=int(n*frac); eval_end=min(origin+30,n-h)
                    origin_date=frame.date.iloc[origin]; end_date=frame.date.iloc[eval_end]
                    fit=ds[ds.target_date < origin_date]
                    ev=ds[(ds.date >= origin_date) & (ds.date < end_date)]
                    if len(ev)<3: continue
                    rm=make_model(kind); rm.fit(fit[FEATURES],fit.target)
                    roll.append(metrics(ev.target,rm.predict(ev[FEATURES])))
                results.append({'target':target,'algorithm':kind,'horizon_days':h,'train_rows':len(tr),'validation_rows':len(va),'test_rows':len(te),'validation':val_metrics,'test':test_metrics,'validation_baselines':val_baselines,'test_baselines':baselines,'rolling_origins':roll})
                candidates.append((val_metrics['mae'],kind))
            if not candidates:
                raise RuntimeError(f'no usable prediction algorithm for {target}/{h}')
            # Select among learned models and transparent data-derived baselines by validation MAE only.
            # Independent test rows never enter model or method selection.
            selected_validation_mae,champion=min(candidates,key=lambda item:(item[0],item[1]))
            final_train=pd.concat([tr,va]).sort_values('target_date')
            key=f'{target}_{h}'
            if champion in ('persistence_baseline','moving_average_7_baseline'):
                model_index[key]={'model':None,'algorithm':champion,'model_version':f'steelchain-{champion}-v1.0.0','artifact_sha256':None,'selected_validation_mae':selected_validation_mae,'features':FEATURES,'feature_version':FEATURE_VERSION,'horizon_days':h,'target':target,'train_start':str(final_train.date.min().date()),'train_end':str(final_train.target_date.max().date()),'data_version':DATA_VERSION,'training_source_sha256':_source_fingerprint(DB)}
            else:
                model=make_model(champion); model.fit(final_train[FEATURES],final_train.target)
                path=OUT/f'{target}_{champion}_{h}d.joblib'; joblib.dump(model,path)
                model_index[key]={'model':str(path.relative_to(ROOT)),'algorithm':champion,'model_version':f'steelchain-{champion}-forecast-v1.0.0','artifact_sha256':_sha256(path),'selected_validation_mae':selected_validation_mae,'features':FEATURES,'feature_version':FEATURE_VERSION,'horizon_days':h,'target':target,'train_start':str(final_train.date.min().date()),'train_end':str(final_train.target_date.max().date()),'data_version':DATA_VERSION,'training_source_sha256':_source_fingerprint(DB)}
            for baseline_name,validation_result in val_baselines.items():
                results.append({'target':target,'algorithm':baseline_name,'horizon_days':h,'train_rows':len(tr),'validation_rows':len(va),'test_rows':len(te),'validation':validation_result,'test':baselines['persistence' if baseline_name=='persistence_baseline' else 'moving_average_7'],'rolling_origins':[]})
    config={'seed':SEED,'data_version':DATA_VERSION,'feature_version':FEATURE_VERSION,'features':FEATURES,'split':{'train':.65,'validation':.15,'test':.20,'ordered_by':'target_date','validation_used_for':'algorithm selection including persistence and moving-average baselines','test_used_for':'final evaluation only'},'horizons_days':HORIZONS,'random_state':SEED,'synthetic_demand_supply_targets':True,'target_process':{'price':'P1日模拟行情区域/品类日均值','demand':'P1采购需求静态总量按年/周季节项及固定趋势构造的日模拟目标','supply':'P1销售挂牌静态总量按年/周季节项及固定趋势构造的日模拟目标'},'algorithms_available':available,'algorithms_unavailable':unavailable,'model_version':MODEL_VERSION,'library_versions':{'xgboost':_version('xgboost'),'lightgbm':_version('lightgbm'),'scikit_learn':_version('scikit-learn'),'pandas':_version('pandas')}}
    joblib.dump({'models':{k:joblib.load(v['model']) for k,v in model_index.items() if v['model']},'index':model_index,'features':FEATURES,'config':config},OUT/'forecast_bundle.joblib')
    (OUT/'training_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    payload={'data_origin':'SIMULATED_MODEL_PREDICTION','data_version':DATA_VERSION,'source_sha256':_source_fingerprint(DB),'rows_daily':n,'split_boundaries':{'train_end_exclusive':str(train_cutoff.date()),'validation_end_exclusive':str(validation_cutoff.date()),'test_end':str(frame.date.iloc[-1].date())},'training_config':config,'results':results,'model_index':model_index,'algorithms_unavailable':unavailable,'limitations':['P1 demand and supply are static snapshots; daily targets are generated by documented synthetic seasonal/trend formulas, not historical observations.','Results characterize simulator behavior and do not represent real market forecast skill.']}
    REPORT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return payload

def predict(target,horizon,as_of=None):
    if target not in ('y','demand','supply') or horizon not in HORIZONS: raise ValueError('unsupported target or horizon')
    frame=load_series(); cutoff=pd.Timestamp(as_of) if as_of else frame.date.max(); hist=frame[frame.date<=cutoff].copy()
    if len(hist)<31: raise ValueError('at least 31 days of history are required')
    ds=features(hist,target,1); row=ds.iloc[-1:]
    bundle=joblib.load(OUT/'forecast_bundle.joblib'); key=f'{target}_{horizon}'
    entry=bundle['index'][key]
    current_source=_source_fingerprint(DB)
    if current_source!=entry['training_source_sha256']:
        raise ValueError('inference data does not match the model training dataset fingerprint')
    if entry['algorithm']=='persistence_baseline': value=float(row.lag_1.iloc[0])
    elif entry['algorithm']=='moving_average_7_baseline': value=float(row.mean_7.iloc[0])
    else:
        model=joblib.load(ROOT/entry['model']); value=float(model.predict(row[FEATURES])[0])
    basis={'persistence_baseline':'预测值取预测时点前一日的已观测值。','moving_average_7_baseline':'预测值取预测时点前连续7个已观测日的均值。'}.get(entry['algorithm'],'已训练回归模型基于日历、1/7/14/30日滞后和7/30日均值特征推理。')
    risk=['所有输入为可复现模拟数据，结果不代表真实市场价格或交易事实。']
    if target in ('demand','supply'):
        risk.append('需求/供应训练目标由静态挂牌总量按显式季节与趋势公式生成，不是历史真实业务量。')
    return {'target':target,'horizon_days':horizon,'as_of':str(hist.date.iloc[-1].date()),'target_date':str((hist.date.iloc[-1]+pd.Timedelta(days=horizon)).date()),'predicted_value':value,'data_origin':'SIMULATED_MODEL_PREDICTION','model':entry['algorithm'],'model_version':entry['model_version'],'artifact_sha256':entry['artifact_sha256'],'feature_version':entry['feature_version'],'features':entry['features'],'training_window':{'start':entry['train_start'],'end':entry['train_end']},'data_version':DATA_VERSION,'training_source_sha256':entry['training_source_sha256'],'inference_source_sha256':current_source,'calculation_basis':basis,'risk_warnings':risk}

\n