# P4/P5 实施与验收报告：多 Agent 决策

## 交付范围
- `steelchain/agents/graph.py`：LangGraph 主流程及五个专业节点（供需预测、行情定价、智能交易匹配、利益优化、合规风控），明确的白名单后端工具接口。
- `steelchain/agents/api.py`：FastAPI `POST /api/v1/assistant/turns` 与 `/health`。
- Pydantic `AgentOutput` 统一 JSON Schema：schema_version、conversation_id、status、role、intent、parameters、results、summary、warnings、data_origin、call_logs。
- 多轮对话使用 conversation_id 关联短期上下文；每次工具调用记录 Agent、工具、耗时与状态；异常转为结构化缺数/HTTP错误。
- LangGraph/LangChain/FastAPI/Pydantic 依赖锁定于 `requirements-agents.txt`。

## 防止虚构事实的约束
主 Agent 不直接产出数值。预测 Agent 只调用 P2 推理函数；当前 P2 LightGBM 原生 DLL 仍报 PermissionError，故价格/需求/供给预测返回 `missing_data`，不输出预测数值。行情定价节点只返回数据库历史模拟行情统计并明确说明这不是预测；匹配、优化、合规结果来自对应数据库/OR-Tools服务。所有结果附 SIMULATED 或缺数标记。

## 测试
`python -m unittest tests.test_agents -v`：5 项通过，包括钢厂采购成本优化、回收商经营建议、自然人额度合规、缺少预测模型不编造数值、多轮主体上下文。全套 `python -m unittest discover -s tests -v` 最终结果需一并运行确认。

## 验收限制
- 意图和角色识别为本地规则解析，没有配置 LLM；支持常见中文关键词，不等同广泛自然语言理解。
- 对话上下文是进程内短期存储与 LangGraph MemorySaver，服务重启会丢失；没有持久化checkpointer。
- 个体预测目前不可用（P2阻断）；因此预测类请求是 partial/needs_data。
- 匹配节点返回候选挂牌，不创建交易；合规检查依赖 P1 快照表，尚无实时鉴权主体上下文。
- 系统无用户认证/租户隔离，生产接入前必须补齐。

## 状态
P4/P5 的 Agent 图、后端工具接口、API契约与三类角色测试已实现。等待验收；未推进 P6。
建议提交：`feat: add LangGraph role-aware decision agents`
