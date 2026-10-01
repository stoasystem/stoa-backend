# E12 infra 新增对话生成 worker 函数与权限

Status: released
Blocked by: 
Decision: [票据 08](../issues/08-runtime-budget-architecture.md)
GitHub: #18

## Delivers

`stoa-conversation-generation` Lambda 存在、可被 API 异步 Invoke、能调 Bedrock 与读写表；sweep 有调度；部署工作流覆盖它。

## Change

stoa-infra `stacks/api_stack.py`：新 `lambda_.Function`（同一 `lambda_code` 资产，PYTHON_3_12/ARM_64，handler `stoa.jobs.conversation_generation.handler`，超时按「模型预算 + 落库余量」设定且远大于 API 的 29 秒，内存与 API 同级）；`production` 别名；IAM：Bedrock `InvokeModelWithResponseStream`/`CountTokens`、表读写、附件桶读；API 函数对 worker alias 的 `lambda:InvokeFunction`；sweep 调度（挂 dispatch-reconciler 现有 `rate(5 minutes)` 或新 Scheduler，周期 ≤ lease）；`deploy-production.yml` 函数名列表；`tests/test_release_topology.py` 的别名与目标断言。

## Acceptance

`cdk synth` 通过；拓扑测试断言新函数只有 production 别名且 Scheduler 目标为 alias；部署角色可更新该函数；在 E11 上线前该函数空转不影响现网。

## Poison

不适用（基础设施）。

## Commit

stoa-infra 单独一个提交，先于 E11 上线；回退只在 E11 已退且没有命令引用 worker 之后。

## Verification

2026-09-24 地图会话核查，提交 `9858946（stoa-infra）`。新增 `stoa-conversation-generation`：同一代码资产、Python 3.12 arm64、1024 MB、超时 3 分钟、handler `stoa.jobs.conversation_generation.handler`、仅 production 别名；IAM 给 `InvokeModelWithResponseStream`、`CountTokens`、表读写、图片桶只读；API production 别名可 invoke worker 别名；5 分钟 Scheduler sweep 带 DLQ 与重试策略，**DISABLED**；部署角色可更新它；环境快照脚本纳入。infra 测试 35 passed（E12 加 6 条）。与票据 E12 的两处差异（部署列表行、API 环境变量 `CONVERSATION_GENERATION_FUNCTION_NAME`）已写进 E11 承接清单；不加环境变量的理由成立（会发布新 API 版本并移别名）。worker 超时 180 秒小于 E11 要求的 lease ≥300 秒，自洽。cdk synth 未在本机复核，以报告为准。

全量后端套件（含两个 release-gate 文件，相邻 infra 目录现已存在）3764 passed / 1 failed，唯一失败是 `test_每个声明出来的lambda都会被后端部署更新`，是 E12 之后有意留红的部署列表检查（见 E18）。infra `tests/` 35 passed。所有提交**尚未推送**。
