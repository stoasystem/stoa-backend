# 被截断的结构化输出应落成失败还是受支持的部分答案（#21）

Labels: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by: 
GitHub: [#21](https://github.com/stoasystem/stoa-backend/issues/21)

## Question

`stop_reason=max_tokens` 加未闭合 JSON 时，`_parse_ai_response` 回退成把原文当 answer，`_provider_result` 只要求 stop_reason 非空，对话路由的形状校验又只看"steps 是列表、answer 非空"。截断内容于是以 `status="sent"` 持久化。buffered 与 stream 两条路径都复现。

要决定：
1. 截断算什么：走既有的可恢复失败边界（学生看到"没答完、可重试"），还是定义一个受支持的"部分答案"终态。issue 明确不要求无条件二次调用模型。
2. 校验放在哪一层：`_provider_result` 直接拒绝 `max_tokens`；还是解析器不再回退成原文，由路由判定。两处各自的投毒方式。
3. 与 #18 的关系：#18 也要改 AI 终态与持久化顺序，本票据的答案要能被 #18 的方案吸收而不是被推翻。
4. `bedrock_max_tokens` 现值是否就是截断的直接原因，需在决议里记下读数而非猜测。

覆盖：stream 与 buffered 各一条截断用例、完整答案对照；JSON 顶层数组的 AttributeError 只记录，不在本票据修。

## Answer

2026-09-24 用户按推荐决议并采纳独立复核的补充约束。

走既有可恢复失败边界，不新增「部分答案」终态。两道检查：
1. `stop_reason == "max_tokens"` 判定**移到解析之前**（两条路径目前都是先 `_parse_ai_response` 再 `_provider_result`），落成 `AIInvocationFailure("incomplete_output")`。
2. 解析后若文本去空白、去代码围栏后仍以 `{` 开头却解析失败，视为残缺 JSON，不得回退成原文答案；`_validate_output` 第 3 步的原文回退不得重新放行它。

约束：抛错前必须先解析并保留 provider 用量证据，让路由 2362 行的恢复路径能观测用量并释放学生预留额度；直接在证据落地前抛错会绕过它。
验收：stream 与 buffered 两条 `max_tokens` 加残缺 JSON 用例 → 失败类别 `incomplete_output`、command 不落 `sent`、预留已释放、用量证据存在；补「`max_tokens` 加完整 JSON」与「`end_turn` 加残缺 JSON」两条，分别只触发一道检查；完整答案两条对照。`bedrock_max_tokens` 当前**代码默认值** 2048，本票据不调。实施票据 [E2](../exec/E02-truncated-output-failure.md)。
