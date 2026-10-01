# 第三次尝试本身中断的对话命令，其额度预留如何收敛（E24 余量）

Labels: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by: 
GitHub: #18

## Question

E24 只结算两类 `failed` 命令：`needs_reconciliation`，以及 E10 留下、未被重试的 `deadline_exceeded`。第三次尝试（`attempt=3`，等于 `MESSAGE_AI_MAX_ATTEMPTS`）本身在 lease 内死掉时，命令走的不是这两条路。E24 票据写的「第三次尝试标 needs_reconciliation」与代码不符。一份预留按命令的 effect 计，三次尝试共用，所以这里卡住的是整条命令的那一份预留，最大时按 `max_output_tokens` 计。

已核实的事实（2026-09-25，在 worker 测试替身上探测）：

1. **lease 到期后 20 分钟内被接手** → 标 `terminal_failed`。sweep 或学生同键重试进入 `generate_for_command`，领取因 `attempt<3` 失败，随后 `mark_message_command_terminal` 写 `status=terminal_failed`、`terminal_at`，只移除 lease 字段。命令上没有 `failure_category`、`failed_at`，E24 的扫描过滤与 `_settlement_due` 都不会选中它；`/generation` 报 `attempts_exhausted`。
2. **`provider_invoked_attempt` 在 `terminal_failed` 上保留**，所以仍能区分「第三次调用过模型」和「死在调用之前」（例如死在 admission 预留之后、调用之前，这是 E10 的形状）。
3. **lease 到期后超过 20 分钟无人接手** → 永远停在 `ai_running`（lease 已过期）。E25 之后的年龄窗口按 `claimedAt` 计，超窗即 `too_old`，sweep 不再碰它。这一类不限于第三次尝试：任何一次尝试在 sweep 失效期间死掉并超窗，都停在这里。上线前的历史命令也可能处于这个状态。
4. **没有任何事件或指标**记录「标 terminal」或「too_old」的发生次数，线上无法估计频率。
5. （读代码所得，未测）第三次尝试若在死前已把答案存到命令上（`provider_result_attempt=3`），标 terminal 的路径不会去看它：已付费的答案被丢弃，effect 停在 `observed`。

要定：

1. **范围**：只收 `terminal_failed`（事实 1），还是把超窗的过期 `ai_running`（事实 3）一并收？
2. **怎么结算**：
   - (a) 扩 E24 的 sweep：`terminal_failed` 按 `terminal_at`、过期 `ai_running` 按 `expiresAt`，超过 N 分钟即走同一条 `release_unknown_cost`。有调用标记的按上限记成本；没有的，effect 若是 `reserved` 仍按上限记（与 E24 对 E10 的保守口径一致），也可以改为只 restore、不记成本（需在账本加一条「确知未调用」的释放路径）。结算后写 `allowance_settled_at`，发同一个事件，复用已有告警。
   - (b) 在标 terminal 的那一刻就同步结算，不等 sweep。事实 3 那类没有这个时机，仍需 sweep。
   - (c) 不做，等周结算自然清零。代价与票据 14 的选项 1 相同。
3. **超窗 `ai_running` 的命令状态**：结算后是否同时标 `terminal_failed`，让 `/generation` 给出终态？还是保持原状、只动账本？
4. **事实 5**：第三次尝试保存下来的答案，是否应先按「已存答案只补完」的规则收尾，再考虑 terminal？这是另一处缺陷还是预期行为？若是缺陷，另立票据还是并入本票据？
5. **可观测性**：是否给「标 terminal」与 sweep 的 `too_old` 各加一个私有事件或指标，以便先读到频率再决定投入？

推荐：范围取 1 的两类都收，结算用 2(a)，并在这之前先上第 5 条的计数。理由：复用 E24 已上线的账本路径与告警，改动集中在 sweep 的候选判定；事实 3 那类只有 sweep 能碰到。第 3 条倾向结算时一并标 `terminal_failed`，否则 `/generation` 对这类命令永远报「进行中」。第 4 条倾向另立票据，它影响的是答案，不只是账本。

## Answer

2026-09-25 用户按推荐决议：
1. 范围两类都收：`terminal_failed`，以及 lease 已过期且超出 sweep 年龄窗口的 `ai_running`。
2. 结算走 2(a)：扩 E24 的 sweep，复用 `release_unknown_cost` 与已有事件、告警；`reserved` 的 effect 一律按上限记成本（与 E24 对 E10 的口径一致），不另加「确知未调用」路径。
3. 超窗的 `ai_running` 结算时一并标 `terminal_failed`，让 `/generation` 给出终态。
4. 第三次尝试存下的答案被丢弃：另立决策票据 [16](16-attempt-three-kept-answer.md)。
5. 先上计数：标 terminal 时发私有事件；sweep 每轮记一行汇总，其中单列超窗的过期 lease 数。计数先上线（E26），结算随后（E27）。
