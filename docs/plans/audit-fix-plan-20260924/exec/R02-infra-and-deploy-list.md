# R02 推 infra 9858946，随即推 E18

Status: released
Blocked by: R01 第 2 步已完成
Decision: [票据 08](../issues/08-runtime-budget-architecture.md)
GitHub: #18
Type: task
Mode: HITL

## Delivers

worker 函数在生产存在且空转；后端 CI 那条部署列表检查回绿。

## Change

1. `git -C stoa-infra push origin main`（9858946）；infra 的 deploy-production 自动 `cdk deploy`；盯 run 到 success；SSO 只读核对 `stoa-conversation-generation` 存在、无 production 别名以外的别名、schedule DISABLED。
2. 立即推后端 E18（部署列表加一行）；盯 run 到 success；核对 `test_每个声明出来的lambda都会被后端部署更新` 在 CI 通过。
两步之间后端 CI 处于被挡窗口，不要在其间推其他后端提交。

## Acceptance

infra run success；后端 run success；worker 函数存在且 schedule DISABLED；四个既有函数别名不变。

## Poison

不适用。

## Commit

无新代码提交（E18 已是独立提交）。push 是部署动作，逐步确认。

## Step 1 record (2026-09-24)

22:06Z 推送 stoa-infra 9858946（c0d79df..9858946）；"Deploy Infrastructure to Production" run 36065554586 success。SSO 只读核对（账号 562923011260）：`stoa-conversation-generation` Active、handler `stoa.jobs.conversation_generation.handler`、timeout 180、仅 `production` 别名 → v1；Scheduler `stoa-conversation-generation` DISABLED，其余三条 ENABLED。

**与票据预期不符**：「四个既有函数别名不变」不成立。infra 流水线自行检出后端 main（653821db）构建 dist 并 `cdk deploy`，把代码重发到所有函数：`stoa-api` production v115 → v116、`stoa-account-deletion` v26 → v27（22:10–22:11Z），CodeSha256 由 `DyCi5IIL…` 变为 `Np6oR9QS…`。run 日志的 provenance 四次校验均为 `sha=653821db… source_tree_hash=adc0ed52b53d`，即同一源码重新构建（zip 非逐字节可复现）。weekly-report v116、dispatch-reconciler v66 为当前值，未与部署前比对。推送后 40 分钟 stoa-api 无调用、无错误。影响：此后每次 infra 部署都会把后端 main 重新发布到全部函数；E22 上线时同样会移动 API 别名，回退计划需按此理解。

## Step 2 record (2026-09-25)

07:48Z 推送 E18（653821db..30a2d7bd，只含该提交）；"Deploy Backend to Production" run 36109520881 success，CI 全量 3830 passed（检出的 infra 已含 worker，部署列表检查通过）。五个函数 production 别名同一 CodeSha256 `sGzj/6qX…`：stoa-api v117、weekly-report v117、dispatch-reconciler v67、account-deletion v28、conversation-generation v2。worker 首次被后端流水线更新，schedule 仍 DISABLED。R02 完成。
