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
if __name__=='__main__': unittest.main()

\n