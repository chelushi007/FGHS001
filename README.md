# 钢链智脑

废钢全链路供需协同与利益优化智能体。目前包含模拟数据、OR-Tools 交易优化、LangGraph Agent/API 和 Next.js 决策工作台。所有数据和计算均为明确标识的模拟输出，不代表真实市场或实盘指令。

## 模拟数据
```powershell
python -m steelchain generate --db data/steelchain.sqlite --seed 20261122 --scenario normal
python -m steelchain validate --db data/steelchain.sqlite
python -m steelchain stats --db data/steelchain.sqlite
```

## Agent API
安装依赖：`python -m pip install -r requirements-agents.txt`。启动开发服务：`uvicorn steelchain.agents.api:app --reload`。

```http
POST /api/v1/assistant/turns
Content-Type: application/json
{"message":"我是钢厂，请优化采购成本","conversation_id":"demo-1"}
```

LangGraph 的五个专业节点调用数据库/优化器/预测工具；预测模型不可用时返回缺数状态，不生成预测数值。对话支持同一进程内按 `conversation_id` 关联上下文。

## 决策工作台（P6）

终端一启动 API：

```powershell
python -m pip install -r requirements-agents.txt
uvicorn steelchain.agents.api:app --reload --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```powershell
cd apps/web
npm ci
$env:NEXT_PUBLIC_API_BASE="http://127.0.0.1:8000"
npm run dev
```

访问 `http://localhost:3000`。`npm run lint` 和 `npm run build` 分别执行 TypeScript 检查与 Next.js 生产构建。工作台会将当前品类挂牌快照和未来系统供需预测分开展示；模型不可用时不显示预测数值。

### 单文件 HTML 智能体

双击仓库根目录的 `钢链智脑服务开关.bat` 启动服务并打开本地 HTML；首次运行会检查并安装依赖，再双击可停止该开关启动的服务。HTML 是单文件界面，Agent 计算仍由 FastAPI 后端提供。分享和部署边界见 [本地 HTML 演示说明](docs/local-html-demo.md)。

## 比赛演示（P7）

```powershell
$env:STEELCHAIN_ENABLE_LIGHTGBM="0"
$env:STEELCHAIN_MODEL_REPORT="reports/P7_MODEL_EVALUATION.json"
python -m steelchain generate --db data/steelchain.sqlite --seed 20261122 --scenario normal --days 1096
python -m steelchain.ml train
python -m steelchain.demo --db data/competition_demo.sqlite --seed 20261122 --scenario normal
python -m unittest discover -s tests -v
```

Compose 启动与比赛讲解顺序见 `docs/deploy.md`、`docs/competition-demo.md`；系统和数据流说明见 `docs/architecture.md`。预测指标及风险见 `reports/P7_MODEL_EVALUATION.md` 和 JSON 明细。

## 优化器
安装 `requirements-optimization.txt` 后：
`python -m steelchain.optimization --role steel_mill|recycler|individual --db data/steelchain.sqlite`

测试：`python -m unittest discover -s tests -v`。阶段详情见 `reports/P1_ACCEPTANCE.md`、`reports/P3_ACCEPTANCE.md`、`reports/P4_P5_ACCEPTANCE.md`、`reports/P6_ACCEPTANCE.md`、`reports/P7_ACCEPTANCE.md`。
