"""Deterministic competition demonstration runner for the simulated system."""
import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _agent_record(result):
    record = result.model_dump()
    for log in record.get('call_logs', []):
        log.pop('duration_ms', None)  # timings are operational metadata, not the demo decision result
    return record


def snapshot_sha256(path):
    con = sqlite3.connect(path)
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='migration_version' ORDER BY name")]
    payload = []
    for table in tables:
        count = len([r[1] for r in con.execute(f'PRAGMA table_info("{table}")')])
        rows = con.execute(f'SELECT * FROM "{table}" ORDER BY ' + ','.join(str(i) for i in range(1, count + 1))).fetchall()
        payload.append((table, rows))
    con.close()
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(',', ':'), default=str).encode()).hexdigest()


def run(db_path, seed=20261122, scenario='normal'):
    db = Path(db_path).resolve()
    db.parent.mkdir(parents=True, exist_ok=True)
    os.environ['STEELCHAIN_DB'] = str(db)
    from steelchain.simulator import generate, validate, stats
    from steelchain.taxonomy import migrate_and_seed
    from steelchain.optimization.quota import reserve_quota, release_quota
    from steelchain.optimization.planner import optimize

    generation = generate(db, seed=seed, scenario=scenario, days=1096)
    try:
        generation['database'] = str(db.relative_to(ROOT))
    except ValueError:
        generation['database'] = db.name
    taxonomy = migrate_and_seed(db)
    reservation = reserve_quota(str(db), 'IN-011', 2025, 'competition-demo:IN-011:2025:001', 10_000)
    duplicate = reserve_quota(str(db), 'IN-011', 2025, 'competition-demo:IN-011:2025:001', 10_000)
    over_limit_rejected = False
    try:
        reserve_quota(str(db), 'IN-011', 2025, 'competition-demo:IN-011:2025:OVER', 5_000_001)
    except ValueError as exc:
        over_limit_rejected = 'quota exceeded' in str(exc)
    release_quota(str(db), 'competition-demo:IN-011:2025:001')

    role_scenarios = {}
    for role, party_id in (('steel_mill', 'ST-001'), ('recycler', 'RE-001'), ('individual', 'IN-011')):
        result = optimize(role, str(db), party_id, year=2025)
        if result['status'] not in ('OPTIMAL', 'FEASIBLE') or not result.get('trades'):
            raise RuntimeError(f'fixed competition scenario is not feasible: {role}/{party_id}')
        role_scenarios[role] = result

    from steelchain.agents import graph
    from steelchain.ml import forecast
    graph.DB = db
    forecast.DB = db
    graph._CONTEXT.clear()
    agent_scenarios = {
        'steel_mill': graph.invoke('我是钢厂，请优化采购成本并列出依据', 'p7-demo-steel', 'steel_mill'),
        'recycler': graph.invoke('我是回收商，请优化经营利润并给出交易路径', 'p7-demo-recycler', 'recycler'),
        'individual': graph.invoke('我是自然人，请检查销售资格和额度', 'p7-demo-person', 'individual'),
    }
    graph.invoke('我是回收商', 'p7-demo-multiturn', None)
    multiturn = graph.invoke('再帮我估算经营利润', 'p7-demo-multiturn', None)

    forecasts = {}
    for target in ('y', 'demand', 'supply'):
        forecasts[target] = {}
        for horizon in (7, 15, 30):
            try:
                forecasts[target][str(horizon)] = forecast.predict(target, horizon)
            except Exception as exc:
                forecasts[target][str(horizon)] = {'status': 'model_unavailable', 'reason': type(exc).__name__, 'data_origin': 'NONE'}

    candidate_matches = graph.tool_matching()
    con = sqlite3.connect(db)
    quota_after = con.execute('SELECT limit_amount,used_amount,reserved_amount FROM quotas WHERE party_id=? AND year=?', ('IN-011', 2025)).fetchone()
    con.close()
    payload = {
        'demo_version': 'p7-fixed-demo-v1',
        'seed': seed,
        'scenario': scenario,
        'business_year': 2025,
        'data_origin': 'SIMULATED',
        'generation': generation,
        'statistics': stats(db),
        'quality_checks': validate(db),
        'database_snapshot_sha256': snapshot_sha256(db),
        'taxonomy': taxonomy,
        'role_scenarios': role_scenarios,
        'matching': candidate_matches,
        'quota_check': {'first_reservation': reservation, 'duplicate_reservation': duplicate, 'over_limit_rejected': over_limit_rejected, 'released_to_baseline': quota_after},
        'agent_scenarios': {k: _agent_record(v) for k, v in agent_scenarios.items()},
        'multiturn_followup': _agent_record(multiturn),
        'forecasts': forecasts,
    }
    if not all(payload['quality_checks'].values()) or not duplicate['duplicate'] or not over_limit_rejected or quota_after != (5_000_000.0, 0.0, 0.0):
        raise RuntimeError('P7 data or quota assertions failed')
    return payload


def main():
    parser = argparse.ArgumentParser(description='Generate fixed simulated competition scenarios and provenance report')
    parser.add_argument('--db', default='data/competition_demo.sqlite')
    parser.add_argument('--seed', type=int, default=20261122)
    parser.add_argument('--scenario', choices=('normal', 'demand_growth', 'demand_decline', 'regional_imbalance'), default='normal')
    parser.add_argument('--report', default='reports/P7_DEMO_RESULTS.json')
    args = parser.parse_args()
    result = run(args.db, args.seed, args.scenario)
    report = Path(args.report)
    if not report.is_absolute():
        report = ROOT / report
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(report), 'database_snapshot_sha256': result['database_snapshot_sha256'], 'quality_checks': result['quality_checks'], 'forecast_algorithms': {k: {h: v.get('model') or v.get('status') for h, v in rows.items()} for k, rows in result['forecasts'].items()}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
