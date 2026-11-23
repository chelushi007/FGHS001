# 本地 HTML 智能体演示

`artifacts/steelchain-agent.html` 是单文件界面，样式、脚本和 SVG 图表均内嵌，不依赖 CDN。它通过 HTTP 请求调用 FastAPI，因此 HTML 本身不能启动 Python Agent、预测模型或 OR-Tools 优化器。

## 本机启动

首次使用先安装 Python 依赖：

```powershell
python -m pip install -r requirements-agents.txt -r requirements-ml.txt -r requirements-optimization.txt
```

双击仓库根目录的 `start-agent-demo.ps1`。脚本会检查或启动本地 API，并打开 HTML 页面。也可以手动在仓库根目录执行：

```powershell
python -m uvicorn steelchain.agents.api:app --host 127.0.0.1 --port 8000
```

然后打开 `artifacts/steelchain-agent.html`。API 健康检查应返回 `status=ok`。浏览器端请求应显示 `SIMULATED` 数据来源。

## 分享给其他人

- 只查看页面外观：直接发送 `artifacts/steelchain-agent.html`。
- 要使用真实 Agent 工具调用：接收者还需要 Python 环境、完整项目源码/依赖和模拟模型数据，安装上述依赖后运行启动脚本。单独的 HTML 文件无法包含或运行 Python 服务。
- GitHub Pages 只能托管静态 HTML，不能运行本项目的 FastAPI 服务。要让他人通过公网交互，需要另行部署带 HTTPS、可公网访问的 API，并为该域名配置 CORS；不要把 `127.0.0.1` 配置成公共 API 地址。

本项目目前未配置公网后端、账号认证或生产级数据隔离；本地演示数据和模型输出均为模拟数据。
