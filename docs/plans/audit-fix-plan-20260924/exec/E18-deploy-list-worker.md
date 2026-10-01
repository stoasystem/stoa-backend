# E18 后端部署列表加入 worker 函数名

Status: released
Blocked by: infra 9858946 已部署（函数存在）；执行见 R02
Decision: [票据 08](../issues/08-runtime-budget-architecture.md)
GitHub: #18

## Delivers

infra 部署 worker 之后，后端 CI 那条「每个声明的 Lambda 都在部署列表里」的检查重新变绿，后续任何后端推送不再被它挡住；不依赖 E11。

## Change

`.github/workflows/deploy-production.yml` 四处 `for function_name in ...` 循环加 `stoa-conversation-generation`。不改 `EXPECTED_HANDLERS`（那是 E11 的，handler 模块此时尚不存在；部署同一 zip 到 worker 无害：无人调用，sweep 为 DISABLED）。

## Acceptance

`tests/test_account_access_decommission.py::test_每个声明出来的lambda都会被后端部署更新` 通过；部署工作流对 worker 的 `update-function-code --dry-run`、更新、等待、发布版本并移 production 别名四步成功；API 行为不变。

## Poison

不适用（配置一行）。

## Commit

单独一个提交，**必须在 infra 9858946 部署完成之后、E11 之前**推送。infra 部署之前推会在 preflight 的 `update-function-code --dry-run` 半途失败。

## Released (2026-09-25)

提交 30a2d7bd，随 R02 第 2 步推送，run 36109520881 success。

2026-09-25 对接：stoa-docs 卡 110 A-08（部署 `upload_cleanup`）将再加一个 Lambda，走同一条顺序规则：infra 先、部署列表行与 `EXPECTED_HANDLERS` 立即跟上。
