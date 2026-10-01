# E5 权益子女集合改用当前关系判据

Status: released
Blocked by: 
Decision: [票据 05](../issues/05-entitlement-current-children-gate.md)
GitHub: [#22](https://github.com/stoasystem/stoa-backend/issues/22)

## Delivers

支付解冻后，反向撤销的家长看不到该孩子的 studentId 与套餐状态。

## Change

`src/stoa/services/entitlement_service.py::_active_child_ids` 正文换成 `[str(link["student_id"]) for link in parent_link_service.current_children(parent_id)]`，删除本地并集逻辑。

## Acceptance

负例：旧 binding 正向 `active`、反向 `revoked`、无其他 link → 权益列表不含该孩子。正例：有效新 link → 包含。既有 entitlement 测试全绿。

## Poison

把正文改回读正向 binding status → 负例红。

## Commit

单独一个提交，提交信息引用票据 06 发布的 issue 编号。

## Verification

2026-09-24 地图会话核查，提交 `6760f124`。负例正对 B-2：旧 binding 正向 active、反向 revoked、无其他 link → 权益列表为空；旧绑定与新 link 各一条正例。既有并集测试改为同时存两行。投毒：改回读正向 binding status → 2 failed。子女顺序变为 link 先于 binding，仅影响列表次序。提交信息注明 issue 待建（票据 06），E5 的 GitHub 字段等 E6 回填。

全量离线回归（排除依赖相邻 infra 根目录的两个 release-gate 文件）3541 passed / 0 failed；`test_formal_release_gate.py` 的一条失败在这五个提交之前的 a015a444 上同样失败，属既有 infra 根目录问题。ruff 对改动文件全部通过；mypy 报错都在未改动的文件里。与远端 origin/main 新增的 4 个提交（b7b1b4f8…ef0827c9）在临时 worktree 里合并无冲突，重叠文件相关 308 条测试通过。五个提交**尚未推送**，未部署。

2026-09-24 补记：提交 amend 为 129c91de 以引用 #22，代码树不变。

## Released

2026-09-24 18:48Z 推送 653821db，"Deploy Backend to Production" run 36043828300 全部步骤 success；18:55Z `stoa-api` production 别名 → v115、`stoa-account-deletion` → v26（同一 CodeSha256 `DyCi5IIL…`），SSO 只读核对（账号 562923011260、AWSReservedSSO 角色）。
