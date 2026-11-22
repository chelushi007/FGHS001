import unittest
import sqlite3
import uuid
from steelchain.optimization.quota import reserve_quota,release_quota
from steelchain.optimization.planner import CostConfig,cost_breakdown,optimize
DB='data/steelchain.sqlite'
class CostTests(unittest.TestCase):
 def test_cost_components(self):
  c=cost_breakdown(2500,2,CostConfig()); self.assertAlmostEqual(c['total'],2500+36+35+50+2500*.08*30/365)
 def test_individual_no_infeasible_recommendation(self):
  con=sqlite3.connect(DB); pid=con.execute("SELECT id FROM parties WHERE role='INDIVIDUAL' ORDER BY id LIMIT 1").fetchone()[0]; con.close()
  r=optimize('individual',DB,pid,2023); self.assertIn(r['status'],('OPTIMAL','FEASIBLE','INFEASIBLE')); self.assertEqual(r['data_origin'],'SIMULATED')
  for trade in r['trades']: self.assertLessEqual(trade['quantity_ton']*trade['recommended_price_per_ton'],5_000_000)
 def test_steel_and_recycler_role_scenarios(self):
  for role in ('steel_mill','recycler'):
   r=optimize(role,DB); self.assertIn(r['status'],('OPTIMAL','FEASIBLE','INFEASIBLE')); self.assertEqual(r['role'],role)
 def test_quota_reservation_is_idempotent(self):
  con=sqlite3.connect(DB); pid=con.execute("SELECT id FROM parties WHERE role='INDIVIDUAL' ORDER BY id LIMIT 1").fetchone()[0]; con.close()
  key='unit-test-'+uuid.uuid4().hex
  a=reserve_quota(DB,pid,2023,key,100.0); b=reserve_quota(DB,pid,2023,key,100.0)
  self.assertFalse(a['duplicate']); self.assertTrue(b['duplicate']); release_quota(DB,key); release_quota(DB,key)
 def test_invalid_role(self):
  with self.assertRaises(ValueError): optimize('person',DB)
if __name__=='__main__': unittest.main()
