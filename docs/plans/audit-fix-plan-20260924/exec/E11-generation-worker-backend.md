# E11 对话生成拆为提交与完成两段，worker 收敛终态

Status: split
Blocked by: E10, E12
Decision: [票据 08](../issues/08-runtime-budget-architecture.md)
GitHub: #18

## Delivers

请求在持久化学生消息、预留与命令后即返回命令标识；生成由 worker Lambda 完成；`GET /conversations/{id}/generation` 返回绑定 command/attempt 的终态；重复投递、lease 到期、跨版本在途命令都有明确收敛路径。

## Change

1. `_execute_message_command` 拆为 `commit_message_command`（写学生消息、预留、命令到 `message_committed`，持久化已解析的 locale、subject、grade、附件提取结果）与 `generate_for_command`（worker 侧）。
2. 路由 `stream_message`/`send_message` 提交后对 worker alias 做异步 `Invoke`，返回 202 与命令标识；Invoke 失败不回滚命令，由 sweep 兜底。
3. 新 `src/stoa/jobs/conversation_generation.py::handler`：条件写领取命令（lease），领取失败即退出；调用前先记录 attempt 与 provider effect id，使 lease 到期后能区分「尚未调用」「已有结果」「结果未知」；只有「尚未调用」重调，「结果未知」进入对账而不重调；生成后在同一处落助手消息、用量证据、命令终态，失败路径显式改写状态与失败类别（与 E2 共用）。
4. `/generation` 返回 `status`（`message_committed`/`ai_running`/`completed`/`failed`）、`attempt`、`assistantMessageId` 或 `failureCategory`、`steps`、`updatedAt`。
5. sweep：扫 `message_committed` 超过 N 秒未领取与 lease 过期的 `ai_running` 命令，按第 3 条规则处理；可挂在 dispatch-reconciler 或独立 job，与 E12 一致。
6. `scripts/build_lambda_dist.py` 的 `EXPECTED_HANDLERS` 加新 handler；`deploy-production.yml` 函数名循环加 `stoa-conversation-generation`。
7. 兼容：新后端能读旧形状命令；回退时在途 `message_committed` 命令由 sweep 标记失败并释放预留。
8. 失败契约沿用 E2：worker 侧的 `AIInvocationFailure` 带 `usage` 时同样观测 provider 成本并释放预留；命令终态的失败类别直接复用 `incomplete_output`、`malformed_response` 与超时三种，不另起一套。

## Acceptance

成功：提交即返回、worker 完成、`/generation` 终态 `completed` 且助手消息一条；重复投递两次只产生一条助手消息、一次扣额；lease 到期三种状态各一条用例，「结果未知」不重调；首 token 慢、早步骤后停滞、worker 在提交后被终止三种，请求结束前学生都能从 `/generation` 拿到明确终态；同一幂等键重试复用原命令；locale 来自命令而非请求头；截断用例走 E2 的 `incomplete_output`；旧形状命令可读。

## Poison

去掉条件领取 → 重复投递那条红；去掉 effect id 记录 → 「结果未知」那条红；去掉 locale 持久化 → 语言那条红。

## Commit

一个提交，被 E10 与 E12 阻塞（需要 worker 函数存在、API 有 Invoke 权限）。上线后监控 `message_committed` 滞留数。回退：revert 本提交，让 sweep 把在途命令标记失败；不承诺零影响。

## Carried over from E12 / E10 (2026-09-24)

- 部署列表行已拆成独立票据 [E18](E18-deploy-list-worker.md)，在 infra 部署后立即推送，不等 E11；E11 只负责 `EXPECTED_HANDLERS` 与 handler 本身。
- infra 给 API 加环境变量 `CONVERSATION_GENERATION_FUNCTION_NAME`（worker alias ARN）；E12 只给了 invoke 权限，没加变量，以免 infra 部署就发布新 API 版本。
- sweep 调度是 `rate(5 minutes)` 且 `DISABLED`；启用前 lease 须 ≥ 300 秒（当前 `_AI_LEASE_SECONDS = 120`），并在 E11 上线时把调度改为 ENABLED。
- worker IAM 只有 `InvokeModelWithResponseStream` 与 `CountTokens`；若 worker 走非流式 `invoke_model`（allowance wrapper 默认方法），需补 `bedrock:InvokeModel`。
- E10 保留的预留（admission 超时后不起生成）只在同一消息重试时被复用；学生不重试则占到周末。worker 设计时决定是否需要回收。

## Split (2026-09-24)

一张票、一个提交装不下这个改动，且中间态必须能单独上线与回退。拆成三张纵向切片，本票据只保留决议与承接清单，不再直接实施：
- [E19](E19-command-commit-and-terminal-status.md) 命令拆两段并暴露终态，生成仍在请求内。
- [E20](E20-generation-worker-handler.md) worker handler 与三态恢复，先不接线。
- [E21](E21-async-cutover.md) 路由切到异步 Invoke，与 infra [E22](E22-infra-cutover.md) 同步。
E13 前端改为被 E19 阻塞（终态字段出现即可开工），并须在 E21 之前上线。
