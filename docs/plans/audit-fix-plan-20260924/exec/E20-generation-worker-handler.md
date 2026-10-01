# E20 worker handler 与 lease 到期三态恢复，先不接线

Status: released
Blocked by: E19, E18（worker 已在部署列表）
Decision: [票据 08](../issues/08-runtime-budget-architecture.md)
GitHub: #18

## Delivers

`stoa.jobs.conversation_generation.handler` 存在并随 zip 部署到 worker 函数：能条件领取一条 `message_committed` 命令并调用 `generate_for_command`；能区分「尚未调用 / 已有结果 / 结果未知」三态；被 Scheduler 事件调用时执行 sweep。此时路由不调用它，sweep 仍 DISABLED。

## Change

新 `src/stoa/jobs/conversation_generation.py`：`handler(event, context)` 分两种 event：直接 Invoke（含 `command_id`、`conversation_id`）与 Scheduler sweep（`job=conversation_generation_sweep`）。领取：条件写 lease（≥300 秒，满足 sweep 周期）；调用前记录 attempt 与 provider effect id；生成走 E19 的 `generate_for_command`；lease 到期规则：无 effect id → 可重调；已有结果 → 只补落库；有 effect id 无结果 → 标 `needs_reconciliation`，不重调。sweep 扫 `message_committed` 超过 N 秒未领取与过期 `ai_running`。`scripts/build_lambda_dist.py` 的 `EXPECTED_HANDLERS` 加新 handler。`_AI_LEASE_SECONDS` 120 → 300。

## Acceptance

重复投递两次只产生一条助手消息、一次扣额；三态各一条用例，「结果未知」不重调；sweep 收敛超时未领取与过期 lease 的命令；handler 被 `boot_smoke` 导入冒烟覆盖；worker IAM 覆盖实际调用的 Bedrock 方法（若用非流式 `invoke_model`，E22 需补 `bedrock:InvokeModel`）。

## Poison

去掉条件领取 → 重复投递那条红；去掉 effect id 记录 → 「结果未知」那条红。

## Commit

单独一个提交，只动后端；上线后 worker 有代码但无人调用。

## Implementation (2026-09-25)

本地提交 1318ffd7，**未推送**。全量 3873 passed；投毒三条（去条件领取、去调用标记、不解绑预算）各转红。

与票据的差异与决定：
- 直接 Invoke 事件为 `{conversation_id, idempotency_key}`（命令按对话+幂等键寻址，command_id 是单向 uuid5）；E21 须按此构造。
- 「effect id 记录」落为 lease 条件写的 `provider_invoked_attempt`（admission 之后、Bedrock 调用之前，写不成则不调用），加上模型返回后保存的 `provider_result_json`；完成与已记录的失败清除二者，故标记在即表示一次未结算的调用。lease 领取以读到的标记为条件。
- `needs_reconciliation` 是 `failed` + 该类别 + 不可重试，不是新状态；预留保持 reserved，对账流程尚不存在。
- 三态规则在 `generate_for_command` 中，学生同键重试同样适用；进程内失败仍按 E19（无用量证据即可重试）。
- sweep 为全表过滤 Scan（无按状态的索引；今日约 6.8k 条 / 4.7 MB，约 5 页），上限 50 页；内联生成、最老优先、剩余 ≥100 秒才开始下一条；跳过 `failed`；`message_committed` 超 60 秒视为未领取。180 秒超时下一次 sweep 实际只能完成约一条慢回答；若 E21 后积压，E22 可考虑自调用扇出（需 lambda:InvokeFunction 于自身）。
- 旧形状命令在 worker 中取 profile 语言、不带弱项主题。
- IAM：worker 恒走流式，现有 InvokeModelWithResponseStream + CountTokens 足够；E22 无需补 `bedrock:InvokeModel`（仍需 E22 核对）。

未修的审查项：leased 写未带 account_fence_generation 条件（删除扫尾会先改状态，条件自然失败）；job 引用 `conversations._ConversationAllowanceFailure` 私有名。

## Verification（地图会话，2026-09-25）

提交 1318ffd7，未推送。与票据对照：`stoa.jobs.conversation_generation.handler` 两种事件（直接 Invoke 带 conversation_id/idempotency_key；Scheduler sweep）；条件领取；三态恢复在 `generate_for_command`：调用前写 `provider_invoked_attempt`（写失败则不调）、答案先存 `provider_result_json`、完成或记录失败时清除；lease 到期后无标记 → 重调，有标记有答案 → 只落库，有标记无答案 → `failed/needs_reconciliation` 不重调；领取条件绑定读到的标记；`EXPECTED_HANDLERS` 加入；`_AI_LEASE_SECONDS` 120 → 300；sweep 扫 `message_committed` 超 60 秒未领取与过期 `ai_running`，剩余运行时 <100 秒即停。新测试 21 条通过；全量 3873 passed；ruff 通过。投毒：领取忽略标记 → 1 failed（过期读取那条）；标记不写入 → 4 failed。

**余量（记入地图）**：1）`needs_reconciliation` 的命令预留一直 reserved，实施方自述「尚无对账」；2）sweep 每 5 分钟对整表做过滤扫描（今天约 5 页，上限 50 页），表大了要稀疏索引；3）推送后 lease 300 秒即对线上请求内生成路径生效，而 sweep 在 E22 之前 DISABLED，硬中断的尝试要等 300 秒才能被同键重试接管；4）E13 的等待上限 240 秒小于 300 秒 lease，见 E13。

## Released (2026-09-25)

11:31Z 推送 1318ffd7（3fd92dc7..1318ffd7），"Deploy Backend to Production" run 36129836249 success，CI 3873 passed，boot smoke handler_count 4；五个函数 production 别名均已移动（含 stoa-conversation-generation）。SSO 令牌过期，未做别名版本只读核对；sweep 仍 DISABLED（未变更）。
