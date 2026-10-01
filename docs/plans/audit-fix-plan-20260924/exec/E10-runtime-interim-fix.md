# E10 AI 调用先受实际剩余运行时约束（阶段性修复）

Status: released
Blocked by: 
Decision: [票据 08](../issues/08-runtime-budget-architecture.md)
GitHub: #18

## Delivers

在 worker 上线之前，AI 调用不再拿着 90 秒预算跑在 29 秒的 Lambda 里：传输层有超时、admission 之后不再盲目起模型、超时前释放预留并给学生一个可恢复失败。

## Change

`routers/conversations.py`：`_ConversationAllowanceBedrockClient` 建 client 时带上与 `ai_service.get_ai_answer` 直调路径相同的 `Config`（connect 5 秒、read 受剩余时间约束、单次尝试）；deadline 以请求开始时刻起算，取 `min(固定预算, Lambda 实际剩余毫秒 − 落库余量)`，剩余时间来自 Mangum 暴露的 Lambda context，本地无 context 时退回固定预算；count_tokens 与 reserve 之后复检 deadline，已超时且尚未调用模型 → 释放预留、落成可恢复失败，不起生成。`ai_service.py`：首个流事件之前也检查 deadline。

## Acceptance

注入时钟：admission 结束时已过 deadline → 无 `invoke_model_with_response_stream` 调用、预留已释放、失败类别为可恢复；剩余运行时 20 秒时 deadline 不超过 20 秒减余量；wrapper 建的 client `Config` 与直调一致（`.scratch/ai-audit-20260924/latency/test_latency_contracts.py` 里那条对照转绿）；10 秒完成的正常答案对照不变。

## Poison

把 Config 去掉 → 对照红；把复检去掉 → admission 超时那条红。

## Commit

单独一个提交，只动后端，可独立 revert。是阶段性修复，不解决 30 秒内答不完的问题。

## Implementation note (2026-09-24)

验收里「预留已释放」按用户决定改为**预留保留**：allowance ledger 只能从 `observed`（有 provider 用量）恢复，不能从 `reserved` 释放；同一消息重试复用同一 effect id，`reserve` 返回 REPLAYED 并沿用原预留，因此不起生成、落可恢复失败、预留留给重试。deadline 只有一个来源：`get_ai_answer(deadline_monotonic=)` 通过 `bind_deadline` 交给 allowance wrapper，wrapper 不另设 deadline。审计 `test_latency_contracts.py` 的 Config 对照与 admission 超时对照转绿；`answer-after-lambda-budget` 仍红，属 E11 范围。

## Verification

2026-09-24 地图会话核查，提交 `750dbff8`。新增 `RequestBudgetMiddleware` 从 Mangum 的 `aws.context` 读剩余毫秒并绑定请求开始时刻；`runtime_budget_service.ai_deadline` 取固定 90 秒与「剩余时间减 4 秒落库余量」的较小者，从请求开始起算，无 context 时退回固定预算；传输配置收敛到 `ai_service.bedrock_runtime_config`，wrapper 与直调共用；`get_ai_answer` 通过 `bind_deadline` 把唯一 deadline 交给 wrapper，admission 后已超时则不起生成；流打开即检查 deadline。新测试 10 条通过。投毒：去掉 wrapper Config → 1 failed；去掉 admission 后复检 → 1 failed；deadline 改从当下起算 → 2 failed。审计延迟契约 7 passed / 1 failed，剩下那条（30 秒完成的答案）是 E11 的。

**与决议的偏离，待用户认可**：票据 08 与 E10 写的是「admission 后超时且未调模型 → 释放预留」，实现改为**保留预留**：额度账本只能在有 provider 用量之后 restore，没调模型就没有用量；同一消息以同一幂等键重试时复用这份预留。代价是学生不重试则该预留占到周结算。理由成立，但这是对已定决议的修改，需你一句认可；已记入 E11 的承接清单。

全量后端套件（含两个 release-gate 文件，相邻 infra 目录现已存在）3764 passed / 1 failed，唯一失败是 `test_每个声明出来的lambda都会被后端部署更新`，是 E12 之后有意留红的部署列表检查（见 E18）。infra `tests/` 35 passed。所有提交**尚未推送**。

## Released

2026-09-24 18:48Z 推送 653821db，"Deploy Backend to Production" run 36043828300 全部步骤 success；18:55Z `stoa-api` production 别名 → v115、`stoa-account-deletion` → v26（同一 CodeSha256 `DyCi5IIL…`），SSO 只读核对（账号 562923011260、AWSReservedSSO 角色）。

2026-09-25 用户认可保留预留（见票据 08 评论）；未重试的预留回收由 E24 承接。
