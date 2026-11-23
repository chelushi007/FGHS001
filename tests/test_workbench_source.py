import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class WorkbenchSourceTests(unittest.TestCase):
 def test_requested_workspaces_and_prompts_are_present(self):
  page=(ROOT/'apps/web/app/page.tsx').read_text(encoding='utf-8-sig')
  for label in ('总览','智能决策','钢厂采购','回收商经营','自然人销售','行情预测','供需分析','交易匹配','合规风控'):
   self.assertIn(label,page)
  self.assertIn('conversation_id',page); self.assertIn('/api/v1/assistant/turns',page)
 def test_simulation_label_and_taxonomy_disclosure(self):
  page=(ROOT/'apps/web/app/page.tsx').read_text(encoding='utf-8-sig')
  for name in ('优质重废','不锈钢304','合金钢废钢'):
   self.assertIn(name,page)
  self.assertIn('REVIEW_REQUIRED',page); self.assertIn('mappingInfo',page); self.assertIn('模拟数据',page)
 def test_echarts_data_comes_from_backend(self):
  charts=(ROOT/'apps/web/components/Charts.tsx').read_text(encoding='utf-8-sig')
  self.assertIn('/api/v1/dashboard/price-series',charts); self.assertIn('/api/v1/dashboard/supply-demand',charts)
  self.assertIn('model_unavailable',charts)
 def test_model_status_is_driven_by_prediction_api(self):
  page=(ROOT/'apps/web/app/page.tsx').read_text(encoding='utf-8-sig')
  self.assertIn('/api/v1/dashboard/supply-demand-forecasts',page)
  self.assertIn('setModelStatus',page)
  self.assertIn('state={modelStatus===',page)
 def test_responsive_navigation_has_mobile_drawer_and_breakpoints(self):
  page=(ROOT/'apps/web/app/page.tsx').read_text(encoding='utf-8-sig')
  css=(ROOT/'apps/web/app/globals.css').read_text(encoding='utf-8-sig')
  self.assertIn('aria-label="打开菜单"',page); self.assertIn('className="scrim"',page)
  self.assertIn('@media(max-width:850px)',css); self.assertIn('@media(max-width:600px)',css)
  self.assertIn('.sidebar.open{transform:translateX(0)}',css); self.assertIn('.main{margin-left:0}',css)
 def test_price_chart_renders_forecasts_from_backend_with_provenance(self):
  charts=(ROOT/'apps/web/components/Charts.tsx').read_text(encoding='utf-8-sig')
  for marker in ('forecasts.forEach','predicted_value','model_version','SIMULATED_MODEL_PREDICTION','forecast_status','SupplyForecastChart','supply-demand-forecasts'):
   self.assertIn(marker,charts)
 def test_standalone_local_agent_calls_api_and_discloses_simulated_data(self):
  html=(ROOT/'artifacts/steelchain-agent.html').read_text(encoding='utf-8-sig')
  api=(ROOT/'steelchain/agents/api.py').read_text(encoding='utf-8-sig')
  for marker in ('/api/v1/assistant/turns','conversation_id','SIMULATED','data_origin','steel_mill','recycler','individual'):
   self.assertIn(marker,html)
  self.assertIn("'null'",api)  # direct file:// browser origin
  self.assertNotIn('https://',html)
  self.assertIn('<script>',html); self.assertIn('</script>',html)
  self.assertIn('forecast.target_date>=currentDate',html)
  self.assertIn('目标日期已过期，暂不展示预测值',html)
 def test_windows_service_switch_resolves_dependencies_from_project_root(self):
  launcher=(ROOT/'service-switch.ps1').read_text(encoding='utf-8-sig')
  batch=(ROOT/'钢链智脑服务开关.bat').read_text(encoding='utf-8-sig')
  self.assertIn('Split-Path -Parent $MyInvocation.MyCommand.Path',launcher)
  self.assertIn('Join-Path $root',launcher)
  self.assertIn('Start-Process',launcher)
  self.assertIn('Stop-Process',launcher)
  self.assertIn('-ExecutionPolicy Bypass',batch)
if __name__=='__main__': unittest.main()
