import hashlib
import json
import math
import sqlite3
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from steelchain.simulator import generate, validate
from steelchain.taxonomy import migrate_and_seed
from steelchain.optimization.quota import reserve_quota, release_quota
from steelchain.optimization.planner import optimize
from steelchain.demo import snapshot_sha256


class CompetitionDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = Path(__file__).resolve().parents[1] / 'data' / 'p7_demo_test.sqlite'
        generate(cls.db, seed=20261122, scenario='normal', days=1096)
        migrate_and_seed(cls.db)

    def test_three_role_scenarios_are_feasible_and_repeatable(self):
        scenarios = [('steel_mill', 'ST-001'), ('recycler', 'RE-001'), ('individual', 'IN-011')]
        for role, party_id in scenarios:
            with self.subTest(role=role):
                first = optimize(role, str(self.db), party_id, year=2025)
                second = optimize(role, str(self.db), party_id, year=2025)
                self.assertIn(first['status'], ('OPTIMAL', 'FEASIBLE'))
                self.assertTrue(first['trades'])
                self.assertEqual(first['data_origin'], 'SIMULATED')
                self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
                for trade in first['trades']:
                    self.assertTrue(trade['constraints'])
                    self.assertGreater(trade['quantity_ton'], 0)
                    if role == 'individual':
                        self.assertLessEqual(trade['quantity_ton'] * trade['recommended_price_per_ton'], 5_000_000)

    def test_quota_reservation_is_idempotent_and_rejects_over_limit(self):
        key = 'p7:individual:STABLE-001'
        first = reserve_quota(str(self.db), 'IN-011', 2025, key, 4_900_000)
        duplicate = reserve_quota(str(self.db), 'IN-011', 2025, key, 4_900_000)
        self.assertFalse(first['duplicate'])
        self.assertTrue(duplicate['duplicate'])
        with self.assertRaisesRegex(ValueError, 'quota exceeded'):
            reserve_quota(str(self.db), 'IN-011', 2025, 'p7:individual:OVER-001', 200_000)
        release_quota(str(self.db), key)
        release_quota(str(self.db), key)
        con = sqlite3.connect(self.db)
        remaining = con.execute('SELECT limit_amount-used_amount-reserved_amount FROM quotas WHERE party_id=? AND year=?', ('IN-011', 2025)).fetchone()[0]
        con.close()
        self.assertEqual(remaining, 5_000_000)

    def test_agent_roles_context_and_explicit_data_origin(self):
        from steelchain.agents import graph
        with patch.object(graph, 'DB', self.db):
            steel = graph.invoke('我是钢厂，请优化采购成本并说明依据', 'p7-steel', 'steel_mill')
            recycler = graph.invoke('我是回收商，请优化经营利润', 'p7-recycler', 'recycler')
            individual = graph.invoke('我是自然人，请检查销售额度和资格', 'p7-person', 'individual')
            graph.invoke('我是回收商', 'p7-multiturn', None)
            follow_up = graph.invoke('再帮我算经营利润', 'p7-multiturn', None)
        for result, role in ((steel, 'steel_mill'), (recycler, 'recycler'), (individual, 'individual')):
            self.assertEqual(result.role, role)
            self.assertEqual(result.data_origin, 'SIMULATED')
            self.assertTrue(result.results)
            self.assertTrue(result.call_logs)
        self.assertEqual(follow_up.role, 'recycler')

    def test_langgraph_forecast_exposes_model_provenance_and_risks(self):
        from steelchain.agents import graph
        from steelchain.ml import forecast
        old_db, old_forecast_db = graph.DB, forecast.DB
        graph.DB = self.db
        forecast.DB = self.db
        try:
            result = graph.invoke('钢厂未来7天价格和供需预测', 'p7-forecast', 'steel_mill')
        finally:
            graph.DB, forecast.DB = old_db, old_forecast_db
        self.assertEqual(result.data_origin, 'SIMULATED_MODEL_PREDICTION')
        self.assertTrue(any('模拟数据模型/基线' in warning for warning in result.warnings))
        self.assertEqual([log['agent'] for log in result.call_logs], ['supply_demand', 'pricing'])
        self.assertIn('model_version', str(result.results))
        self.assertIn('calculation_basis', str(result.results))
        self.assertIn('risk_warnings', str(result.results))

    def test_all_forecast_horizons_have_model_provenance(self):
        from steelchain.ml import forecast
        bundle_path = forecast.OUT / 'forecast_bundle.joblib'
        self.assertTrue(bundle_path.exists(), 'run python -m steelchain.ml train before the P7 test suite')
        original_db = forecast.DB
        forecast.DB = self.db
        try:
            for target in ('y', 'demand', 'supply'):
                for horizon in (7, 15, 30):
                    with self.subTest(target=target, horizon=horizon):
                        result = forecast.predict(target, horizon)
                        self.assertEqual(result['data_origin'], 'SIMULATED_MODEL_PREDICTION')
                        self.assertTrue(result['model_version'])
                        self.assertTrue(result['data_version'])
                        self.assertTrue(result['training_source_sha256'])
                        self.assertTrue(result['inference_source_sha256'])
                        expected_date = date.fromisoformat(result['as_of']) + timedelta(days=horizon)
                        self.assertEqual(result['target_date'], expected_date.isoformat())
                        self.assertTrue(math.isfinite(result['predicted_value']))
                        self.assertTrue(result['calculation_basis'])
                        self.assertTrue(result['risk_warnings'])
        finally:
            forecast.DB = original_db

    def test_model_report_keeps_validation_test_and_source_separate(self):
        report = Path(__file__).resolve().parents[1] / 'reports' / 'P7_MODEL_EVALUATION.json'
        self.assertTrue(report.exists(), 'run python -m steelchain.ml train before the P7 test suite')
        payload = json.loads(report.read_text(encoding='utf-8'))
        self.assertEqual(payload['data_origin'], 'SIMULATED_MODEL_PREDICTION')
        self.assertTrue(payload['source_sha256'])
        self.assertEqual(set(payload['model_index']), {f'{target}_{h}' for target in ('y', 'demand', 'supply') for h in (7, 15, 30)})
        self.assertEqual(payload['training_config']['split']['test_used_for'], 'final evaluation only')
        self.assertTrue(all(result['validation_rows'] > 0 and result['test_rows'] > 0 for result in payload['results']))
        self.assertTrue(all('test_baselines' in result for result in payload['results'] if result['algorithm'] not in ('persistence_baseline', 'moving_average_7_baseline')))

    def test_compose_contains_healthchecks_and_persistent_simulated_db(self):
        compose = (Path(__file__).resolve().parents[1] / 'docker-compose.yml').read_text(encoding='utf-8')
        self.assertIn('healthcheck:', compose)
        self.assertIn('steelchain-data:/app/data', compose)
        self.assertIn('NEXT_PUBLIC_API_BASE: http://localhost:8000', compose)

    def test_api_bootstraps_fixed_simulated_database_from_empty_path(self):
        from steelchain.agents.api import ensure_simulated_database
        db = Path(__file__).resolve().parents[1] / 'data' / 'p7_api_bootstrap.sqlite'
        ensure_simulated_database(db)
        con = sqlite3.connect(db)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM parties').fetchone()[0], 122)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM prices').fetchone()[0], 1096 * 6 * 20)
        con.close()

    def test_repeat_generation_clears_migrated_ledger_and_maps(self):
        generate(self.db, seed=20261122, scenario='normal', days=1096)
        migrate_and_seed(self.db)
        baseline_hash = snapshot_sha256(self.db)
        reserve_quota(str(self.db), 'IN-011', 2025, 'p7:repeat:001', 100)
        generate(self.db, seed=20261122, scenario='normal', days=1096)
        migrate_and_seed(self.db)
        self.assertEqual(snapshot_sha256(self.db), baseline_hash)
        self.assertTrue(all(validate(self.db).values()))
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM quota_ledger').fetchone()[0], 0)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM category_taxonomy_map').fetchone()[0], 20)
        con.close()

    def test_refuses_forecast_for_different_scenario_source(self):
        from steelchain.ml import forecast
        different_db = Path(__file__).resolve().parents[1] / 'data' / 'p7_growth_test.sqlite'
        generate(different_db, seed=20261122, scenario='demand_growth', days=60)
        original_db = forecast.DB
        forecast.DB = different_db
        try:
            with self.assertRaisesRegex(ValueError, 'fingerprint'):
                forecast.predict('demand', 7)
        finally:
            forecast.DB = original_db


if __name__ == '__main__':
    unittest.main()
