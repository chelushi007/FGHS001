# 部署手册

## Docker Compose 比赛演示

前置条件：安装 Docker Engine 和 Docker Compose v2，并确保 3000/8000 端口可用。

```powershell
docker compose config
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://localhost:8000/health
Invoke-WebRequest http://localhost:3000 -UseBasicParsing
```

首次启动 API 会在持久卷 `steelchain-data` 中生成 seed `20261122`、normal 情景、1096 天行情的固定模拟业务库，并执行数据质量检查。`docker compose down` 保留数据库；`docker compose down -v` 会删除演示卷并在下次启动时重建。

浏览器访问 `http://localhost:3000`。浏览器端 API 地址在 Web 镜像构建时通过 `NEXT_PUBLIC_API_BASE` 设定，默认 `http://localhost:8000`。如果比赛设备不在 Docker 宿主机上访问，应把该值改成宿主机可达的地址后重新构建 Web 镜像。

## 本地联调

```powershell
python -m pip install -r requirements-agents.txt -r requirements-ml.txt -r requirements-optimization.txt
python -m steelchain generate --db data/competition_demo.sqlite --seed 20261122 --scenario normal --days 1096
$env:STEELCHAIN_DB="data/competition_demo.sqlite"
uvicorn steelchain.agents.api:app --host 127.0.0.1 --port 8000
```

另开终端：

```powershell
cd apps/web
npm ci
$env:NEXT_PUBLIC_API_BASE="http://127.0.0.1:8000"
npm run dev
```

若要复现 P7 评估，请使用固定的 normal 模拟库并执行：

```powershell
$env:STEELCHAIN_DB="data/steelchain.sqlite"
$env:STEELCHAIN_ENABLE_LIGHTGBM="0"
$env:STEELCHAIN_MODEL_REPORT="reports/P7_MODEL_EVALUATION.json"
python -m steelchain.ml train
```

训练完成会写入 `artifacts/models`、`artifacts/models/training_config.json` 和 P7 JSON 指标报告。演示发布时须将这些模型制品与应用镜像一同发布。

## 运维检查

- `GET /health` 返回状态和 `SIMULATED` 来源标识。
- `python -m steelchain validate --db <path>` 检查外键、库存、额度、订单、物流、来源标签和三年日行情。
- `python -m steelchain.demo --db <path>` 运行比赛场景并写出结果报告。
- 当前仅适用于离线比赛演示；无认证、租户隔离、TLS、PostgreSQL 适配和生产级备份策略。
