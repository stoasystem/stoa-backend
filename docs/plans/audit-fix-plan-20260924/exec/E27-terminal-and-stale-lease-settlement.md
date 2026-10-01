# E27 terminal_failed 与超窗过期 lease 的预留按「成本未知」结算

Status: released
Blocked by: E26 已上线
Decision: [票据 15](../issues/15-terminal-failed-reservation.md)
GitHub: #18

## Delivers

第三次尝试本身中断的命令、以及 lease 过期后无人接手超出窗口的命令，不再永久占住一份预留；走 E24 的同一条结算路径与告警。

## Change

`attachment_repo`：扫描过滤加入 `terminal_failed` 且无 `allowance_settled_at`；新增条件写「关闭超窗 lease」（`ai_running`、leaseOwner 与 expiresAt 与读到的一致、已过期 → `terminal_failed`、`terminal_at`，移除 lease 字段）；E24 的条件写按（状态, 时间字段）泛化到 `terminal_failed`/`terminal_at`。`jobs/conversation_generation.py`：候选加 `terminal_failed` 且 `terminal_at` 超过 10 分钟，以及过期且超窗的 `ai_running`（先关闭再结算，同一轮完成）；`release_unknown_cost` → 写 `allowance_settled_at` → 释放时发 `conversation_ai_needs_reconciliation_settled`。

## Acceptance

第三次尝试调用后死 → sweep 标 terminal → 10 分钟后结算：预留归零、成本等于上限、evidence 一条、命令带 `allowance_settled_at`；第三次尝试已观测用量的只 restore；超窗过期 lease → 同一轮标 `terminal_failed` 并结算，`/generation` 报终态；窗口内的过期 lease 仍由 sweep 生成而不被结算；再跑一次不重复。

## Poison

去掉「超窗」条件 → 窗口内过期 lease 被误结算那条红；去掉关闭 lease 的 expiresAt 条件 → 并发续约那条红。

## Commit

后端一个提交；不动 infra（复用 E24 告警）。上线会一次性结算历史积压，告警会有一批。

## Implementation (2026-09-25)

本地提交 47a603c2，**未推送**。扫描过滤加入 `terminal_failed` 且无 `allowance_settled_at`；E24 的条件写泛化为（状态, 结束时间字段），映射 `attachment_repo.SETTLEMENT_ENDED_AT` 一处；新增 `close_stale_lease`（ai_running、leaseOwner 与 expiresAt 等于读到的值、已过期 → `terminal_failed`/`terminal_at`，移除 lease 字段、保留调用标记）。sweep：`terminal_failed` 在 `terminal_at` 满 10 分钟后结算；超窗过期 lease 同一轮先关闭再结算；待结算列表按各自结束时间排序。新用例 6 条，全量 3908 passed。
投毒：去掉「超窗」条件 → 「窗口内过期 lease 只生成不结算」红；去掉关闭写里 leaseOwner/expiresAt 的相等条件 → 「读后被重试接手的 lease 不被关闭」红。偏离：票据写的第二条投毒「并发续约」不成立（过期 lease 不能续约），改为「读后学生重试又死、lease 也已过期」，此时只有相等条件拦得住。
上线须知：首轮会结算历史上全部 `terminal_failed` 与超窗 `ai_running`，每条真实释放各发一次告警；超窗命令会从「进行中」变为 `attempts_exhausted`。若票据 16 日后决定补完第三次尝试存下的答案，这类命令的预留届时已被 restore，补完路径需要容忍（effect 已 restored）。

## Released (2026-09-25)

47a603c2，run 36189913895 success。首轮 sweep 起会结算历史积压，告警预期有一批。

## Verification（地图会话，2026-09-25）

47a603c2 已上线。与票据 15 逐条对上：扫描加入 `terminal_failed` 且无 `allowance_settled_at`；条件写按（状态, 结束时间字段）泛化；`close_stale_lease` 以 leaseOwner 与 expiresAt 相等且已过期为条件把超窗 lease 改为 `terminal_failed`，同一轮结算；`terminal_failed` 满 10 分钟结算；复用 E24 的释放与告警。新用例 6 条通过；全量 3913 passed。投毒：去掉「超窗」条件 → 1 failed；去掉 leaseOwner/expiresAt 相等条件 → 1 failed。实施记录里对票据第二条投毒的修正（过期 lease 不能续约，改为「读后被重试接手」）成立。

线上：E27 部署（21:08Z）后 sweep 持续运行，`conversation_ai_needs_reconciliation_settled` 事件 0 条、告警 OK、DLQ 0，即没有历史积压需要结算；报告里「预期会收到一批告警」未发生，与 E22 时「等待中命令 0 条」一致。
