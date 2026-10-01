# E9 PDF 结构预校验搬进受限子进程

Status: released
Blocked by: E08
Decision: [票据 10](../issues/10-pdf-prevalidation-isolation.md)
GitHub: #6

## Delivers

恶意 PDF 的结构解析在 CPU/内存受限的子进程里被终止，API 进程只做魔数检查；附件不会在校验未完成时进入 `validated`。

## Change

`file_validation_service.validate_pdf`：保留 `%PDF-` 检查，把 PdfReader、加密、>500 页、mediabox 遍历搬进 `document_parser_worker` 的受限子进程入口；父进程按结果映射 `UPLOAD_INVALID`/`UPLOAD_CONTENT_MISMATCH`；超时、SIGXCPU、非零退出一律 `UPLOAD_INVALID`。`attachment_service` 两个调用点（1648、2583）契约不变。

## Acceptance

畸形长对象头输入 → 子进程终止、`UPLOAD_INVALID`、无 500；加密与 >500 页仍拒；正常 PDF 通过；子进程超时不放行；探针覆盖结构校验本身（不只魔数）；现有抽取隔离测试不变。

## Poison

去掉超时 → 不放行那条红；把 PdfReader 移回父进程 → 终止那条红。

## Commit

单独一个提交，被 E8 阻塞。

## Readings after E8 (2026-09-24)

`pypdf==6.19.0` 本地重跑 `.scratch/ai-audit-20260924/prior-issues/pdf_validation_probe.py`（合成输入，子进程 3 CPU 秒 / 6 秒墙钟限制）：64 KiB 头 → `ValidationFailure`，解析 0.0005 秒（子进程墙钟 0.62 秒，含启动）；4 MiB 头（4,194,540 字节）→ `ValidationFailure`，解析 0.0172 秒（墙钟 0.34 秒）。6.14.2 时同一 4 MiB 输入在 ~3.01 秒被 SIGXCPU 终止（`returncode=-24`）。探针只覆盖这两组输入；结构校验仍在 API 进程内，E9 的隔离仍需做。

## Readings after E9 (2026-09-24)

同一探针，结构校验已在受限 worker 子进程内：64 KiB 头 → `ValidationFailure`，0.268 秒；4 MiB 头 → `ValidationFailure`，0.281 秒（均为 spawn + 子进程解析；E8 后进程内解析为 0.0005 / 0.017 秒，差值是 spawn 成本）。每次 PDF 上传校验多约 0.27 秒。

## Verification

2026-09-24 地图会话核查，提交 `0e419007`（实施方未在报告中单列，随 R01 第一步一并进入待推送集合，本次补核）。

与票据 10 决议一致：API 进程只读 `%PDF-` 魔数；strict 解析、加密、>500 页、mediabox 遍历全部搬进 `document_parser_worker` 的 spawn 隔离进程（CPU 3 秒、地址空间、墙钟 8 秒的既有限制）；任何非干净答案（拒绝、超时、被杀、spawn 失败）→ `UPLOAD_INVALID`；无魔数仍 `UPLOAD_CONTENT_MISMATCH` 且不解析；`attachment_service` 两个调用点契约不变；`pypdf` 不再被 API 进程导入。新测试 14 条通过（正常与恰好 500 页放行，加密、501 页、审计 4 MiB 对象头拒绝，超时不放行，API 进程被禁用 PdfReader 时合法 PDF 仍放行，worker 干净答案为空文本）。相关套件（attachment security、phase473 document boundary、saved attachments）合计 308 passed。投毒：忽略时限 → 1 failed（超时那条）；改回 API 进程解析 → 7 failed（含隔离那条）。

代价：每次 PDF 上传校验多一次 spawn，本机实测约 0.27 秒。可接受，记入地图。

## Released

2026-09-24 18:48Z 推送 653821db，"Deploy Backend to Production" run 36043828300 全部步骤 success；18:55Z `stoa-api` production 别名 → v115、`stoa-account-deletion` → v26（同一 CodeSha256 `DyCi5IIL…`），SSO 只读核对（账号 562923011260、AWSReservedSSO 角色）。
