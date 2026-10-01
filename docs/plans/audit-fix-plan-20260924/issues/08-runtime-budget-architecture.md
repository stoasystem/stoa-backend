# AI 回答应在请求内完成还是搬到独立生命周期（#18）

Labels: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by: 07
GitHub: [#18](https://github.com/stoasystem/stoa-backend/issues/18)

## Question

API Lambda 29 秒，AI deadline 90 秒且在准备工作之后才起算，lease 120 秒，stream 路由在完整生成结束后才构造 SSE。硬终止时学生消息与额度预留已写、助手答案未写、command 卡在 `ai_running`。

基于票据 07 的事实，决定：
1. 方向：(a) 把整条请求压进剩余运行时（更小 max_tokens、更早的 deadline、admission 后复检、超时落成可恢复终态）；(b) 生成搬到独立 worker（SQS + Lambda 或直接异步调用），请求只返回 command 状态，前端沿用已有轮询拿终态；(c) Lambda Function URL 流式响应绕开 API Gateway。各自要改哪几个仓库、回退是否仍是"一条 revert"。
2. 不论方向，allowance wrapper 必须带上与直调相同的 transport Config，admission 之后要复检 deadline；这两条是否单独一个提交先上。
3. 终态模型：请求结束时学生必须拿到"答案"或"可恢复的失败"之一，且没有无限期 `ai_running`；lease 到期后谁负责收尾。与票据 02 的截断终态合并成一套。
4. 幂等：重试复用同一个 idempotencyKey，不重复扣额度、不重复写学生消息。

覆盖：成功、首 token 慢、早步骤后停滞、学生消息与预留提交后终止；每种都要在请求结束前落成明确终态。决议后把 Not yet specified 里的前端/infra 契约问题变成新票据。

## Answer

2026-09-24 用户按推荐选方向 B，并采纳独立复核的五条约束。

**方向 B**：请求把学生消息、额度预留与命令持久化到 `message_committed` 后即返回；生成由独立 worker Lambda 完成；前端轮询命令终态。触发用 API Lambda 对 worker 的异步 `Invoke`，Scheduler 加 lease 的模式兜底（与 account-deletion 相同）。不选 A（HTTP API v2 的 30 秒不可提高、模型延迟未测，压预算证不了不再超时）；不选 C（Python 运行时不原生流式，Function URL 无 JWT 授权器，等于换接入层）。

**先行提交（E10，阶段性修复）**：allowance wrapper 带上与直调相同的 transport Config；deadline 以请求开始时刻起算并受**实际剩余运行时间**约束，不是固定 90 秒；admission 之后若已超时且尚未调用模型，释放预留并落成可恢复失败。worker 的 deadline、lease 与落库余量在 E11 统一设计，并与票据 02 的终态及用量处理一致。

**约束**：
1. 提交与完成分开。请求返回已持久化的命令标识与查询入口；后台在明确期限内收敛到终态。异步 Invoke 的 202 只表示入队，且可能重复投递（AWS 异步调用语义）。
2. 恢复以持久命令为准。worker 用条件写领取命令，重复投递不重复写学生消息、不重复扣额度。Scheduler 覆盖「命令已写、Invoke 尚未执行」的空隙与过期 lease。lease 到期不得直接重调模型：必须区分「尚未调用」「已有结果」「调用结果未知」三种状态，只有「尚未调用」可以重调。
3. 补齐异步上下文。请求里解析好的 locale、subject、grade、附件提取结果随命令持久化，worker 不再读 `Accept-Language`。状态与进度绑定 command 与 attempt；前端重试与页面恢复复用原幂等键。
4. 终态模型与票据 02 合并：请求结束时学生拿到「答案」或「可恢复失败」之一；`ai_running` 不再靠 lease 到期解锁，失败路径显式改写命令状态；截断、超时、provider 错误共用一套失败类别与用量处理。
5. 三仓上线顺序 infra → 后端 → 前端；回退顺序反向：前端先退，后端退时在途命令由 sweep 收敛或显式标记失败，infra 最后退且只在没有命令再引用 worker 之后。后台命令可能跨版本存活，不承诺整个方向 B 靠一次 revert 回退；E10 单独可 revert。

实施票据：[E10](../exec/E10-runtime-interim-fix.md)、[E11](../exec/E11-generation-worker-backend.md)、[E12](../exec/E12-generation-worker-infra.md)、[E13](../exec/E13-frontend-terminal-polling.md)。Not yet specified 里的「前端与 infra 契约」已随本决议落成 E12、E13。

## Comments

2026-09-24 核查 E10（750dbff8）：实现与本决议「admission 后超时且未调模型 → 释放预留」不同，改为保留预留并由同一幂等键的重试复用。理由：额度账本只在有 provider 用量之后才能 restore，未调模型即无用量可记。**待用户认可**；认可后本条改写为「保留预留，E11 统一设计回收」，不认可则 E10 需补一条无用量的释放路径。

2026-09-25 用户认可：E10「admission 超时且未调模型」时**保留预留**、由同一幂等键的重试复用，本决议先行提交那条据此改写；未重试的预留回收并入票据 14 的「无用量证据的释放」路径（E24）。

## #18 closure draft (2026-09-26，发出前需用户确认)

> Fixed by moving answer generation out of the API request (direction B), deployed 2026-09-24 to 2026-09-26.
>
> - **Interim bound** (750dbff8): the AI call is bounded by the time the Lambda actually has left, with a single-attempt client, so an answer can no longer outlive its invocation.
> - **Commit and generate as two steps** (3fd92dc7): the request only stores the student's message, quota claim and a command carrying the answer's context; the command ends in an explicit terminal state reported by `GET /conversations/{id}/generation`.
> - **Worker** (1318ffd7, infra 9858946 / 813c538, 30a2d7bd): a separate Lambda generates the answer under a conditional lease. The API invokes it asynchronously (7c8d46e0), and a 5-minute sweep picks up what the invoke missed (86cbf0af, c93dce94). An attempt whose Lambda died is recovered by what it left: generated again if the model was never called, finished from the stored answer if one was kept (1f2c9097 for a last attempt), `needs_reconciliation` otherwise, never calling the model twice.
> - **Frontend** (stoa-frontend 3aae4b2, e347fc7, ad40c74): the chat follows the command to its terminal state by polling, waits past the backend's lease, and marks failed or stopped answers.
> - **Allowance** (87e4cf54, 7372f58e, 47a603c2, infra 2cec071): a reservation whose outcome is unknown is released after 10 minutes with its cost recorded at the reservation's ceiling, and each release alerts `stoa-alerts` (`stoa-conversation-needs-reconciliation-settled`).
>
> Verification: the offline suite (3918 passed at 5714aebf) runs the real route, worker and repository against the shared table double, including lost-invoke, lease-expiry, duplicate-delivery and paid-but-lost cases. Production smoke on 2026-09-26 with a test student account: two questions (math, physics) were committed and answered through the worker, with the chat polling `/generation` to completion. That is two live conversations, not a load or latency measurement.

## #18 closed (2026-09-26)

用户确认草稿原文。评论 https://github.com/stoasystem/stoa-backend/issues/18#issuecomment-5840569134 已发，#18 `CLOSED` / `COMPLETED`；回读最后一条评论与草稿逐字一致。
