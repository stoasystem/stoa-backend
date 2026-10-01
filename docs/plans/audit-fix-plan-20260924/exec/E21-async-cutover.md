# E21 路由切到异步 Invoke，前端已就绪后再切

Status: released
Blocked by: E20, E13, E22
Decision: [票据 08](../issues/08-runtime-budget-architecture.md)
GitHub: #18

## Delivers

答不完 29 秒的问题不再被 Lambda 掐断：请求提交后异步 Invoke worker 并立即返回命令标识与查询入口；前端轮询终态；sweep 兜底。

## Change

`routers/conversations.py`：当 `settings.conversation_generation_function_name` 非空时，`commit_message_command` 之后对 worker alias 做 `InvocationType=Event` 的 Invoke 并返回 202 与命令标识，不再在请求内生成；为空时保持 E19 的请求内生成（回退开关）。Invoke 失败不回滚命令，交给 sweep。`config.py` 加该设置。

## Acceptance

开关开：提交即返回、worker 完成、`/generation` 终态；Invoke 抛错 → 命令留在 `message_committed`、sweep 收敛；开关关 → 行为与 E19 相同。注入 30 秒完成的答案：请求在 29 秒前返回，终态由轮询取得（审计延迟契约最后那条转绿）。

## Poison

让 Invoke 失败回滚命令 → sweep 那条红。

## Commit

单独一个提交，与 E22 同一窗口上线：先 E22（env var、ENABLED），后本提交；回退先关开关（E22 回退 env var）再 revert 本提交。

2026-09-25 补记（来自 R02 的发现）：infra 流水线每次 `cdk deploy` 都会检出后端 main 重新构建并发布到全部函数。因此 E22 部署时后端 main 上是什么就发布什么：E21 若已在 main，切换会随 infra 部署一起发生；E21 若不在，E22 只是加变量与启用 sweep。回退同理：改回 infra 变量也会重新发布后端 main。上线时按这个理解排序：E22 先（此时 main 无 E21），E21 后。

## Implementation (2026-09-25)

本地提交 7c8d46e0，**未推送**。E22 已把变量设在 API 上，所以推送即切换生产。全量 3886 passed。投毒：Invoke 失败回滚命令 → 丢失 Invoke 那条红；跳过重开 → 三条重试测试红。

决定：
- 三个入口（消息、流式、新建对话首条）统一走 `_submit_message_command`；已有答案的命令仍在请求内回放；202 体 `{conversationId, commandId, idempotencyKey, status, studentMessage}`。
- Invoke 有界（connect 2 s、read 3 s、单次），失败只记日志不回滚，sweep 一分钟后接手。
- 同键重试可重试的失败：请求返回前把命令条件改回 `message_committed`（仅当该失败仍是最新 attempt），否则前端并行轮询会先读到旧的 failed、且重试的 Invoke 丢失后 sweep 接不到（审查发现的阻断项）。只有学生会重开失败，重复投递仍视失败为 settled。
- 审查确认：API 对 worker alias 的 invoke 权限已由 E12 授予；配额仍在 commit 时扣；预留与 E10 的重试复用在共享的 `generate_for_command` 内；账户删除围栏随命令携带。

回退：先在 infra 删掉 API 变量（会重发后端 main），再 revert 本提交。

## Verification（地图会话，2026-09-25）

提交 7c8d46e0，未推送。与票据对照：`settings.conversation_generation_function_name` 非空即 `commit_message_command` 后异步 Invoke（`InvocationType=Event`，connect 2 秒 / read 3 秒 / 单次尝试）并返回 202 `MessageAcceptedResponse`；为空即 E19 的请求内生成（回退开关）；Invoke 失败只记日志不回滚，交给 sweep（60 秒未领取即接手）；同键重试 `failed` 且可重试的命令先条件写回 `message_committed`（`reopen_failed_message_command`，绑定 attempt）；三个入口（messages、stream、新会话首条）统一走 `_submit_message_command`；已有答案仍在请求内回放。新测试 12 条通过；全量 3889 passed；ruff 过。投毒：跳过 reopen → 3 failed；忽略开关恒走请求内 → 10 failed。审计延迟契约里「30 秒答案在 29 秒前返回」那条在开关打开的等价测试（`test_an_answer_longer_than_the_gateway_waits_no_longer_holds_the_request`）里转绿。

前端核对：建会话只发 `{subject, grade}`，首条消息随后走 E13 的流式钩子（`setQueuedInitialMessage`），后端 `initialMessage` 的 202 路径没有前端消费者，无缺口。

**推送即切换**：API v121 已带变量。回退：先在 infra 删变量（会重新发布后端 main），再 revert 本提交。

## Released (2026-09-25)

19:4xZ 推送 86cbf0af..8433b39e（E21 加 E23），"Deploy Backend to Production" run 36181425450 两个 job 均 success。推送即切换：API 变量已在，切换随本次发布生效。

## Production reading（地图会话，2026-09-26，SSO 只读）

2026-09-25 22:21Z 与 22:23Z 两次真实对话走完了方向 B 的全链路（API Gateway 访问日志 + worker 日志，内容不可见，只有元数据）：

| 时刻（UTC） | 发送 | worker 生成 | 答案可见 |
|---|---|---|---|
| 22:21:55 | `POST /conversations/<id>/messages/stream` → **202**，414 ms | 22:21:59 `ai_request_started` → 22:22:09 `ai_response_received`（10.5 秒，含 2.5 秒冷启动） | 22:22:11 前端重取会话；轮询 `/generation` 7 次（1,1,1,2,2,3,5 秒节拍）全部 200 |
| 22:23:20 | 同上 → **202**，407 ms | 22:23:20 → 22:23:32（12.0 秒） | 22:23:35 重取会话；轮询 7 次全部 200 |

发送到答案可见约 15–16 秒；请求本身 0.4 秒返回，不再持有到答案生成完。期间 0 条 5xx、worker 0 条失败、三条告警 OK、之后每轮 sweep `candidates=0 stale_leases=0 reconciled=0`。唯一异常是 22:22:35 一次 `GET /conversations/<id>` 401（单次，无重试，疑为登录测试的令牌切换），与本路径无关。

边界：两次生成都在 10–12 秒内完成，本身没有超过 29 秒；这次读数证明的是「202 + 轮询 + worker」的机制在线上成立，不是「超过 29 秒的答案也能完成」的实测。后者只有离线注入 30 秒答案的测试（`test_an_answer_longer_than_the_gateway_waits_no_longer_holds_the_request`）。
