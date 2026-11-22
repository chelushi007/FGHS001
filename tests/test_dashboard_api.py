import unittest
from fastapi.testclient import TestClient
from steelchain.agents.api import app
class DashboardApiTests(unittest.TestCase):
 def setUp(self): self.client=TestClient(app)
 def test_price_series_is_simulated_and_ordered(self):
  x=self.client.get('/api/v1/dashboard/price-series?days=14').json(); self.assertGreaterEqual(len(x['history']),7); self.assertEqual(x['data_origin'],'SIMULATED'); self.assertEqual(x['history'],sorted(x['history'],key=lambda p:p['date'])); self.assertIn(x['forecast_status'],('available','model_unavailable'))
  if x['forecast_status']=='available':
   self.assertEqual([p['horizon_days'] for p in x['forecasts']],[7,15,30])
   self.assertTrue(all(p['model_version'] and p['calculation_basis'] and p['risk_warnings'] for p in x['forecasts']))
 def test_supply_demand_snapshot_schema(self):
  x=self.client.get('/api/v1/dashboard/supply-demand').json(); self.assertEqual(len(x['items']),20); self.assertTrue(all('demand_ton' in i and 'supply_ton' in i for i in x['items'])); self.assertEqual(x['data_origin'],'SIMULATED')
 def test_supply_forecasts_are_provenanced_or_explicitly_unavailable(self):
  x=self.client.get('/api/v1/dashboard/supply-demand-forecasts').json()
  self.assertIn(x['forecast_status'],('available','model_unavailable'))
  if x['forecast_status']=='available':
   self.assertEqual(len(x['forecasts']),6)
   self.assertEqual(x['data_origin'],'SIMULATED_MODEL_PREDICTION')
   self.assertTrue(all(f['model_version'] and f['calculation_basis'] and f['risk_warnings'] for f in x['forecasts']))
  else:
   self.assertEqual(x['forecasts'],[])
 def test_cors_and_overview(self):
  r=self.client.get('/api/v1/dashboard/overview',headers={'Origin':'http://localhost:3000'}); self.assertEqual(r.status_code,200); self.assertEqual(r.headers.get('access-control-allow-origin'),'http://localhost:3000')
if __name__=='__main__': unittest.main()
