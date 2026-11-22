import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from steelchain.agents.api import app

class AgentE2ETests(unittest.TestCase):
 def setUp(self): self.c=TestClient(app)
 def test_steel_mill_cost_optimization(self):
  r=self.c.post('/api/v1/assistant/turns',json={'message':'我是钢厂，请帮我优化采购成本','conversation_id':'e2e-steel'}).json()
  self.assertEqual(r['role'],'steel_mill'); self.assertEqual(r['intent'],'optimize'); self.assertTrue(r['results']); self.assertEqual(r['data_origin'],'SIMULATED')
 def test_recycler_profit_optimization(self):
  r=self.c.post('/api/v1/assistant/turns',json={'message':'我是回收商，优化经营利润','conversation_id':'e2e-recycler'}).json()
  self.assertEqual(r['role'],'recycler'); self.assertEqual(r['intent'],'optimize'); self.assertTrue(r['results'])
 def test_individual_compliance_sell_only(self):
  r=self.c.post('/api/v1/assistant/turns',json={'message':'我是自然人，检查销售额度合规','conversation_id':'e2e-person'}).json()
  self.assertEqual(r['role'],'individual'); self.assertEqual(r['intent'],'compliance'); self.assertIn('compliance',str(r['results'])); self.assertEqual(r['status'],'ok')
 def test_prediction_missing_is_not_fabricated(self):
  from steelchain.ml import forecast
  with patch.object(forecast,'predict',side_effect=RuntimeError('test model unavailable')):
   r=self.c.post('/api/v1/assistant/turns',json={'message':'钢厂未来7天价格预测','conversation_id':'e2e-missing'}).json()
  self.assertIn(r['status'],('partial','needs_data')); self.assertIn('缺少可用预测模型',str(r['warnings']))
 def test_multiturn_role_context_and_schema(self):
  first=self.c.post('/api/v1/assistant/turns',json={'message':'我是回收商','conversation_id':'multi'}).json()
  second=self.c.post('/api/v1/assistant/turns',json={'message':'再帮我算利润','conversation_id':'multi'}).json()
  self.assertEqual(second['schema_version'],'1.0'); self.assertEqual(second['role'],'recycler')
if __name__=='__main__': unittest.main()
