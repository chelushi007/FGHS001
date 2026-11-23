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
 def test_role_specific_responses_include_results_and_bounded_trade_detail(self):
  from steelchain.agents.graph import invoke
  prompts=(('steel_mill','我是钢厂，请优化采购成本'),('recycler','我是回收商，请优化经营利润'),('individual','我是自然人，请优化销售净收益'))
  responses=[invoke(prompt,'role-output-'+role,role) for role,prompt in prompts]
  summaries=[response.summary for response in responses]
  self.assertIn('ST-001',summaries[0]); self.assertIn('预计到厂成本',summaries[0])
  self.assertIn('RE-001',summaries[1]); self.assertIn('卖方税前净额',summaries[1])
  self.assertIn('IN-011',summaries[2]); self.assertIn('模拟额度',summaries[2])
  self.assertEqual(len(set(summaries)),3)
  for response in responses:
   optimization=next(result for result in response.results if result.get('agent')=='optimization')
   self.assertLessEqual(len(optimization['trades']),10)
   self.assertGreaterEqual(optimization['trade_count'],len(optimization['trades']))
 def test_expired_prediction_is_not_presented_as_a_current_forecast(self):
  from steelchain.agents.graph import invoke
  response=invoke('我是钢厂，未来7天价格和供需预测','stale-forecast-check','steel_mill')
  self.assertEqual(response.status,'needs_data')
  self.assertIn('早于当前日期',response.summary)
  self.assertTrue(any('过期预测' in warning for warning in response.warnings))
  def collect_predictions(value):
   if isinstance(value,dict):
    own=[value] if value.get('data_origin')=='SIMULATED_MODEL_PREDICTION' else []
    return own+sum((collect_predictions(item) for item in value.values()),[])
   if isinstance(value,list): return sum((collect_predictions(item) for item in value),[])
   return []
  predictions=collect_predictions(response.results)
  self.assertTrue(predictions)
  self.assertTrue(all(item.get('predicted_value') is None and item.get('stale') for item in predictions))
if __name__=='__main__': unittest.main()
