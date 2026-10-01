# E24 结果未知与未重试的预留按「成本未知」结算，并告警

Status: released
Blocked by: E21 已上线
Decision: [票据 14](../issues/14-needs-reconciliation-reservation.md)
GitHub: #18

## Delivers

一条 `needs_reconciliation` 的命令不再永久占住学生的一份最大预留：超过 10 分钟即 restore 预留、成本按预留上限记账；每次发生有告警送到 `stoa-alerts`。E10 留下的「admission 超时未调模型且学生未重试」的预留走同一条路。

## Change

后端：`allowance_service` 新增「无用量证据的释放」路径（restore 预留、provider cost 记为预留上限、evidence 标 `unknown_cost`）；`jobs/conversation_generation.py` 的 sweep 加一类候选：`failed` 且 `failure_category=needs_reconciliation` 且 `failed_at` 超过 10 分钟且 effect 仍 `reserved`/`observed`，以及 `failed/deadline_exceeded` 且 `retryable` 但 `failed_at` 超过 20 分钟未被重试的（E10 余量）；结算后在命令上写 `allowance_settled_at` 防重复；发 `conversation_ai_needs_reconciliation_settled` 私有事件。infra：按卡 111 形状加一条基于该事件指标（或 log metric filter）的告警，动作 `stoa-alerts`。

## Acceptance

模拟「模型已调用、答案未存、lease 到期」→ 第三次尝试标 needs_reconciliation → 10 分钟后 sweep 结算：预留归零、provider cost 等于预留上限、evidence 一条、命令带 `allowance_settled_at`；再跑一次 sweep 不重复结算；E10 场景 20 分钟未重试同法；正常完成与可重试失败的命令不被结算；infra 告警资源存在且有 action。

## Poison

去掉 `allowance_settled_at` 条件 → 重复结算那条红；把结算窗口改为 0 → 正常完成命令被误结算那条红。

## Commit

后端一个提交、infra 一个提交；infra 部署会重新发布后端 main，先后端后 infra。

## Implementation (2026-09-25)

后端 87e4cf54、infra 2cec071，均**未推送**（先后端后 infra）。账本 `allowance_repo.release_unknown_cost`：`reserved` → 按预留上限记 provider cost（evidence 带 `cost_basis=unknown_cost`）→ restore；`observed` 只 restore；已 finalized/restored → ALREADY_SETTLED；无 effect → NOTHING_RESERVED。sweep：先把命令关闭重试（`failure_retryable=false`，条件 failed_at 未变、无 `allowance_settled_at`），再结算，最后写 `allowance_settled_at`；只有真正释放才计 `reconciled` 并发 `conversation_ai_needs_reconciliation_settled`。infra：worker 日志 metric filter + 告警 `stoa-conversation-needs-reconciliation-settled` → `stoa-alerts`。测试 9 条；投毒：去掉 `allowance_settled_at` 条件 → 「不重复结算」红；窗口改 0 → 「近期不结算」两条红（「正常完成不被结算」那条不受窗口影响，因扫描只取两类 failed）。全量 3900 passed，infra 37 passed。
偏离/待拍板：(1) E10 候选不再要求 retryable（被本 sweep 关闭重试后中断的命令下轮须能收尾）；(2) 结算后该命令同键不可再重试；(3) 第三次尝试本身死亡时命令落 `terminal_failed`、无 failure_category，其预留不在本票据范围内，仍无出路；(4) 首次上线会一次性结算历史积压，每条释放都发告警。

## Verification（地图会话，2026-09-25）

后端 87e4cf54 与 infra 2cec071，均未推送。与票据 14 逐条对上：sweep 扫描加入 `failed` 且类别为 `needs_reconciliation`/`deadline_exceeded` 且无 `allowance_settled_at` 的命令；分别在 10 / 20 分钟后结算；顺序为先 `close_failure_for_settlement`（关同键重试）→ `release_unknown_cost`（仍 reserved 的按预留上限记 `cost_basis=unknown_cost` 的用量，已 observed 的保留原用量，再 restore）→ 发 `conversation_ai_needs_reconciliation_settled` 事件 → `mark_allowance_settled`；中途中断由下一轮续完且不重复计费（有专门用例）。infra：worker 日志 metric filter 匹配 `event_category=conversation_ai_needs_reconciliation_settled`（与 `emit_private_event` 的输出格式逐字一致），5 分钟内 ≥1 即告警到 `stoa-alerts`。新测试 9 条通过；全量 3900 passed；ruff 过；infra 37 passed。

投毒读数：把 `needs_reconciliation` 的等待窗口改为 0 → 1 failed（「近期的先不结算」那条）。**票据里「去掉 `allowance_settled_at` 条件 → 重复结算那条红」不成立**：去掉命令级条件、去掉扫描侧过滤、去掉账本 ALREADY_SETTLED 短路三层各去一层，`test_a_settled_command_is_not_settled_again` 仍 9 passed。原因是最底层 `_complete_allowance` 对已 restore 的 effect 拒绝再次 restore，性质由它兜住；上两层是冗余防线，测试只验性质不验每层。不是缺陷。建议在推送前把该测试加两条断言：第二轮 `again["settled"] == 0` 且 `again["errored"] == 0`（即已结算命令根本不再是候选），这样扫描侧过滤被去掉时会红。

## Released (2026-09-25)

推送前按核查意见补断言（9956aa9b）：第二轮 sweep `reconciled/settled/errored` 全为 0，即已结算命令不再是候选。单独去掉任一层 `allowance_settled_at` 条件（扫描过滤、`_settlement_due`、条件写）仍绿，因为另两层兜住；三层一起去掉 → 该条红。后端 8433b39e..9956aa9b run 36186080005 success；随后 infra 2cec071 run 36186922615 success，MetricFilter 与告警 `stoa-conversation-needs-reconciliation-settled` 均 CREATE_COMPLETE（据部署日志；本机无 AWS 凭据未直接回读）。
