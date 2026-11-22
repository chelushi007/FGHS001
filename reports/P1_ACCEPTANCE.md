# P1 模拟数据与数据库验收报告

## 实施范围
建立 SQLite 可执行数据库与 SQL 迁移、三类主体/20类品类/库存/区域日行情/采购需求/销售供给/订单/物流/自然人年度额度模型；提供固定随机种子的四情景生成命令、初始化、统计及数据质量检查。

## 复现方式
```powershell
python -m steelchain generate --db data/steelchain.sqlite --seed 20261122 --scenario normal
python -m steelchain validate --db data/steelchain.sqlite
python -m steelchain stats --db data/steelchain.sqlite
python -m unittest discover -s tests -v
```

情景：`normal`、`demand_growth`、`demand_decline`、`regional_imbalance`。所有数据均由合成规则生成并标记 `SIMULATED`，不得解释为真实市场观测。

## 数据规模（seed=20261122，normal）
| 数据表 | 行数 |
|---|---:|
| 主体 | 122（钢厂12、回收商30、自然人80）|
| 废钢品类 | 20 |
| 库存 | 920 |
| 日行情 | 131,520（1,096天×6区域×20品类）|
| 行情日期 | 1,096 |
| 销售供给 | 920 |
| 采购需求 | 840 |
| 交易订单 | 840 |
| 物流单 | 840 |
| 自然人年度额度账户 | 240（80人×3年）|

## 数据质量与业务规则检查
2026-11-22 本地执行 `python -m steelchain validate --db data/steelchain.sqlite`，以下全部为 true：外键完整；自然人无采购需求；年度额度上限为 5,000,000 且未超额；订单关联的挂牌与需求品类一致且数量不超限；库存预留不超库存；物流容量覆盖订单量；数据来源标记正确；品类数为20；行情覆盖至少三年日历日期。

自动化测试：`python -m unittest discover -s tests -v`，3 项通过（全量生成与质量检查、固定种子统计可复现、非法情景拒绝）。

## 已知限制与风险
- 采用 SQLite 与 Python 标准库实现，方便本地可复现；PostgreSQL/SQLAlchemy 迁移与 Compose 尚未落实，需后续阶段补齐。
- 行情是明确的合成价格过程，不能作真实市场预测。需求增长/下降场景改变生成需求规模；区域失衡改变区域价格系数，需业务方审阅参数。
- 当前业务订单是模拟的已完成样本，模型未覆盖质量维度与真实路由网络；库存以预留量呈现，不包含完整收发流水。
- quota 采用金额硬上限模拟，不构成反向开票税务解释。

## 验收结论
P1 本地数据生成、数据库迁移、自动化测试和数据质量报告已完成。等待用户验收，未开始下一阶段。

建议 Git 提交：`feat: add reproducible simulated scrap data foundation`
