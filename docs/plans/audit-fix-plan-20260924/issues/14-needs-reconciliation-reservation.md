# 结果未知的对话命令，其额度预留如何收敛（E20 余量）

Labels: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by: 
GitHub: #18

## Question

E20 之后，模型已被调用（`provider_invoked_attempt` 已写）、答案未保存、lease 到期的命令被标为 `failed` + `needs_reconciliation`、不可重试，从不重调模型（票据 08 约束 2）。它的 allowance effect 停在 `reserved`（按 `max_output_tokens` 预留），账本只能在有 provider 用量之后 restore，所以这份预留没有出路；若在 observe 之后才丢失，则停在 `observed`。学生看到可见失败，只能以新幂等键重发，新消息另起一份预留。

要定：
1. 等周结算自然清零（不做任何事；代价：该周学生可用额度被一份最大预留占住，直到周结算）；还是
2. 加对账：按「成本未知」释放——例如 sweep 发现 `needs_reconciliation` 超过 N 分钟即 restore 预留、成本记为未知/按上限记 provider cost；需要账本新增一条「无用量证据的释放」路径（E10 当初没有做的那条）；还是
3. 查 Bedrock 侧（CloudWatch 调用日志、request id 未持久化）补回真实用量后再结算——需先把 provider request id 在调用前持久化。

同时要定：`needs_reconciliation` 是否需要告警（卡 111 的形状），以及 R01 之后的线上读数怎么判断它的发生频率（预期极少：只在 Lambda 于模型调用与保存答案之间被杀时出现）。

## Answer

2026-09-25 用户按推荐决议：**选项 2 加告警**。sweep 发现 `needs_reconciliation` 超过 N 分钟（建议 10 分钟，等于两轮）即按「成本未知」结算：restore 预留，provider cost 按该次预留上限记（不低估成本），账本新增一条「无用量证据的释放」路径（E10 当初留下的那条）；停在 `observed` 的命令同法只做 restore。每次发生发 `conversation_ai_needs_reconciliation` 私有事件并接一条 CloudWatch 告警（按卡 111 形状，动作 `stoa-alerts`）。不选 1（学生一周少一份最大预留）与 3（Bedrock 无按请求查用量的接口，且需先持久化 request id）。实施票据 [E24](../exec/E24-needs-reconciliation-settlement.md)。
