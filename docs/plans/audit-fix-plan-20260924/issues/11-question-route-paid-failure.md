# question 路由上带用量证据的 AI 失败应如何处置（E2 余量）

Labels: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by:
GitHub: [#21](https://github.com/stoasystem/stoa-backend/issues/21)

## Question

E2（972cefe2）让 `AIInvocationFailure` 带上 `usage`，conversations 路由据此观测用量并释放预留。questions 路由没接：`routers/questions.py` 的两处失败分支只把 `response_cleanup_failed` 视为 terminal，`incomplete_output` 与 `malformed_response` 落成 `provider_outcome_unknown`，用量证据丢弃。既有恢复逻辑会在学生重放同一命令时再调一次模型，过期则按 exact-once 补偿退还预留，所以不是泄漏，但成本证据丢了，已知结果被当成未知，重放多半再截断一次。

带用量证据的失败该走哪条路：terminal 加补偿、还是保持 unknown 等重放？

## Answer

2026-09-24 用户按推荐决议。

带 `usage` 的 `AIInvocationFailure` 视为**已知 provider 结果**：先用失败上的用量证据观测 provider 成本（与成功路径同一条 `_observe_question_provider_usage` 语义），再按既有 terminal 路径标记 `provider_rejected` 并补偿预留；不标 `provider_outcome_unknown`，不靠学生重放再调模型。不带 `usage` 的失败（连接失败、超时）维持现状走 unknown。实施票据 [E14](../exec/E14-question-route-paid-failure.md)。
