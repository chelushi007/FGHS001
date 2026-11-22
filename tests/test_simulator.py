import unittest
from pathlib import Path
from steelchain.simulator import generate, validate, stats
class SimulatorTests(unittest.TestCase):
 def setUp(self): self.db=str(Path(__file__).resolve().parents[1]/'data'/'test.sqlite')
 def test_generates_consistent_simulated_dataset(self):
  generate(self.db,seed=17,days=1096); self.assertTrue(all(validate(self.db).values())); s=stats(self.db)
  self.assertEqual(s['categories'],20); self.assertEqual(s['prices'],1096*6*20); self.assertGreater(s['orders'],0)
 def test_fixed_seed_reproducible(self):
  generate(self.db,seed=99,days=10); a=stats(self.db); generate(self.db,seed=99,days=10); self.assertEqual(a,stats(self.db))
 def test_scenario_rejects_invalid(self):
  with self.assertRaises(ValueError): generate(self.db,scenario='real_market',days=1)
if __name__=='__main__': unittest.main()
