# E8 升级 pypdf 到 6.19.0 并重审依赖例外

Status: released
Blocked by: 
Decision: [票据 10](../issues/10-pdf-prevalidation-isolation.md)
GitHub: #6

## Delivers

PDF 解析器不再受 GHSA-fc8x-2rww-xw9m 与 GHSA-763m-79hh-57f2 影响；dependency policy 在当前时间与当前锁下通过。

## Change

`uv lock --upgrade-package pypdf`，重新导出 `requirements.txt`；按 dependency policy 流程重签 `evidence/phase-474/dependency-exceptions.json` 的 ecdsa 例外（新 `lock_sha256`、理由、到期），不手改哈希。

## Acceptance

`pypdf==6.19.0` 在 uv.lock 与 requirements.txt；`validate_exception_ledger(ledger, now=datetime.now(UTC))` 通过；`tests/test_dependency_policy.py` 全绿；重跑 `pdf_validation_probe.py` 记录升级后两组输入的解析时长。

## Poison

不适用（依赖变更）。

## Commit

单独一个提交，先于 E9。

## Verification

2026-09-24 地图会话核查，提交 `0404cf3c`。uv.lock 与 requirements.txt 只有 pypdf 6.14.2 → 6.19.0；.venv 已装 6.19.0。例外账本重签：`lock_sha256` 等于当前 uv.lock 的 SHA-256（f8011b0c…），到期 2026-12-21 不变，可达性说明重核；`validate_exception_ledger(now=now)` 通过，钉住例外身份的两条测试随之更新。探针复跑：64 KiB 输入 0.0006 秒拒绝、4 MiB 输入 0.017 秒拒绝，与报告一致（6.14.2 时 4 MiB 被 3 CPU 秒外部限制杀掉）。**待用户确认**：账本 `approval_evidence` 写的是「Owner directed ticket E8 in Claude Code conversation on 2026-09-24」，与事实相符（用户 2026-09-24 对 Q7 说「同意」），且被测试钉住原句。结构校验仍在 API 进程，E9 未做。

全量后端套件（含两个 release-gate 文件，相邻 infra 目录现已存在）3764 passed / 1 failed，唯一失败是 `test_每个声明出来的lambda都会被后端部署更新`，是 E12 之后有意留红的部署列表检查（见 E18）。infra `tests/` 35 passed。所有提交**尚未推送**。

## Released

2026-09-24 18:48Z 推送 653821db，"Deploy Backend to Production" run 36043828300 全部步骤 success；18:55Z `stoa-api` production 别名 → v115、`stoa-account-deletion` → v26（同一 CodeSha256 `DyCi5IIL…`），SSO 只读核对（账号 562923011260、AWSReservedSSO 角色）。

2026-09-25 用户认可账本 `approval_evidence` 的措辞（Owner directed ticket E8 in Claude Code conversation on 2026-09-24）。
