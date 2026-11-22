# P7 比赛演示系统验收报告

## 已交付

- `steelchain.demo`：固定 seed `20261122`、normal 情景、业务年 2025，生成/校验比赛 SQLite，并运行钢厂采购、回收商购销、自然人销售、额度幂等预留与超额拒绝、交易候选、Agent 和 9 组价格/需求/供应预测。结果写入 `reports/P7_DEMO_RESULTS.json`。
- 修复模拟器重建逻辑：重新生成前清除额度流水与三级品类映射并重置流水序列，避免后续迁移数据阻止重复演示。
- 预测实验改进：验证集对比 XGBoost 和持平/7日均值基线后选型，独立测试集只报告；推理增加模型/基线版本、制品哈希、训练窗口、模型数据版本、训练/推理源表指纹、计算依据、目标日期与风险提示。推理拒绝不匹配情景的数据源。
- 增加 Compose 双服务、API/Web Dockerfile、持久模拟数据卷、容器健康检查、启动时固定种子建库和校验；明确当前数据库为 SQLite。
- 交付 [架构说明](../docs/architecture.md)、[部署手册](../docs/deploy.md)、[比赛演示脚本](../docs/competition-demo.md) 与 [模型评估报告](P7_MODEL_EVALUATION.md)。

## 实测结果

- `python -m unittest discover -s tests -v`：34 项通过（含预测模型状态与后端可用性一致的前端回归断言）。
- 预发布模型训练：`STEELCHAIN_ENABLE_LIGHTGBM=0; STEELCHAIN_MODEL_REPORT=reports/P7_MODEL_EVALUATION.json; python -m steelchain.ml train` 成功，使用 XGBoost 与两个基线。模型评估窗口和每项指标见报告。
- 固定演示脚本运行两次：质量检查全部通过；输出 JSON SHA-256 两次相同：`3C019E05B9D27C780F1FD9BC713E06ACA94CBC90F41013112C4D2201E01D9B44`（不含机器绝对路径和调用耗时）；数据库业务快照 SHA-256 两次相同：`d1fd2d4d8e388e74826b0295bc824dbd264a61b9ffa1eeee51509cd38fb4009d`。
- 固定业务规模：122 主体、20 品类、920 库存、131,520 价格行（1096 日）、920 供给挂牌、840 采购需求、840 订单、840 物流、240 自然人年度额度账户。
- 三类固定优化场景：钢厂 `ST-001`、回收商 `RE-001`、自然人 `IN-011` 均返回 OPTIMAL 且有交易分配。自然人单笔建议受剩余额度约束；固定测试还验证同键预留幂等、超额拒绝、释放重复调用安全。
- 后端用例覆盖多轮回收商角色继承、钢厂/回收商优化、自然人额度合规、供需与价格多 Agent 预测元数据和风险提示。
- 独立 Uvicorn HTTP 冒烟：健康端点 200；价格预测端点返回 3 个周期，供需预测端点返回 6 个目标/周期；预测对话返回 `SIMULATED_MODEL_PREDICTION`、模拟风险提示及 `supply_demand,pricing` 执行记录；省略角色的后续轮次继承为 recycler 并完成 optimize。
- 固定模拟数据库 HTTP 对话复测：钢厂采购优化、回收商经营优化、自然人额度合规均返回 `status=ok` 与 `SIMULATED` 来源；回收商第二轮不传角色时继承 recycler。
- Chrome 生产页面手工冒烟：页面显示 122 主体、920 条供给、840 条需求和 840 笔订单；价格图显示 7/15/30 天模拟模型预测已加载；浏览器网络日志确认供需、行情和对话请求到达 FastAPI 并返回 200。联调发现预测模型状态原先硬编码不可用，现改为查询后端供需预测状态，并加入自动化回归。
- TypeScript `node node_modules/typescript/bin/tsc --noEmit`、Python 编译检查、Next.js 生产构建均通过。生产构建使用已锁定的 `@next/swc-wasm-nodejs`（本机 Windows SWC DLL 无法加载），并通过 `NEXT_TEST_WASM_DIR` 指定本地 WASM；页面静态生成成功。
- `npm ls --depth=0` 显示直接依赖齐全。环境默认 `NPM_CONFIG_OFFLINE=true`；普通 `npm ci` 遇到 `ENOTCACHED`，在线模式虽能补齐锁定包和安装目录，但 npm 进程在结束阶段持续挂起，未把它记为干净安装通过。Next 15.5.29 tarball 已按 package-lock 的 SHA-512 摘要校验。
- Compose YAML 用 PyYAML 解析通过并核对两个服务与健康检查；这不是容器启动测试。

## 阻断项与未执行项

- Docker Engine/Compose 未安装（`docker` 命令不存在），所以 Compose 构建、容器启动与容器健康检查不能在本机实测。配置与镜像脚本已交付，不能据 YAML 解析声称 Docker 验收通过。
- Playwright/Selenium 驱动未安装，没有自动浏览器 E2E 或移动端视口截图；已完成 Chrome 桌面页面手工冒烟及真实 HTTP 链路复测。
- `npm ci` 在当前 npm/Windows 环境未能正常结束；虽然依赖树齐全、TypeScript 和生产构建通过，仍需在干净环境运行 `cd apps/web; npm ci; npm run build` 验证可复现安装。
- LightGBM DLL 导入在当前 Windows 环境出现 `PermissionError (WinError 5)`。P7 发布 bundle 以 XGBoost/确定性基线为选型，保留 P2 LightGBM 比较报告；比赛镜像须按文档安装模型依赖。
- 现有 P4/P5 进程内对话、无身份认证、无租户隔离及 SQLite 与原设计 PostgreSQL 差异，限制了公网/生产部署。Compose 是离线比赛演示部署，不是生产部署。
- 价格模拟集的持平基线预测没有趋势信号；需求/供应预测训练目标是公式合成数据。展示须沿用“模拟”来源及风险说明。

## 结论

固定数据、三角色业务场景、额度规则、预测可追溯信息、浏览器桌面页面和重复演示一致性已通过代码/运行验证。P7 当前为部分验收：Docker 实际构建/启动仍需 Docker Engine；自动化浏览器 E2E 仍需 Playwright/Selenium；npm 干净安装仍需定位当前 Windows npm 收尾挂起。不能将这些未通过项表述为全部验收。

建议提交标题：`feat: complete P7 competition demo and acceptance`
