# PDF 结构预校验应升级依赖还是搬进受限解析进程（#6）

Labels: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by: 
GitHub: [#6](https://github.com/stoasystem/stoa-backend/issues/6)

## Question

`file_validation_service.validate_uploaded_file` 在 API 进程里直接 `PdfReader(stream, strict=True)`，早于隔离的抽取 worker；锁文件钉 `pypdf==6.14.2`，受 CVE-2026-82398（6.15.0 修）与 XForm 抽取问题（6.16.1 修）影响。65 KB 合成输入解析约 3 秒，4 MB 输入被外部 6 秒闸打断。

要决定：
1. 依赖：升到哪个版本、走现有 dependency policy 流程（`scripts/dependency_policy.py`、`evidence/phase-474/dependency-exceptions.json`）怎么记录；升级是否单独一个提交先上。
2. 隔离：结构预校验搬进已有的受限抽取进程，还是在 API 进程里给它加 CPU/墙钟闸；两者对上传完成延迟的影响。
3. 升级后 DoS 是否仍可达：决议要有升级后重跑 `pdf_validation_probe.py` 的读数，而不是只看 advisory 列表。
4. 覆盖：畸形输入、进程被终止、正常 PDF 对照；现有抽取隔离不变。

## Answer

2026-09-24 用户按推荐决议并采纳独立复核的补充约束。

两个提交。E8：pypdf 6.14.2 → 6.19.0（2026-09-16 发布，覆盖 GHSA-fc8x-2rww-xw9m 与 GHSA-763m-79hh-57f2），走 uv lock 与 requirements 导出；锁变化后 `evidence/phase-474/dependency-exceptions.json` 里 ecdsa 例外绑定的 `lock_sha256` 失效，必须按 dependency policy 流程重审例外，不手改哈希；`validate_exception_ledger(now=now)` 通过。E9：`validate_pdf` 的 PdfReader 部分搬进 `document_parser_worker` 受限子进程（CPU/内存 rlimit 已在），保留现有加密、>500 页、结构拒绝规则；附件进入 `validated` 之前必须拿到子进程的校验结果，超时或进程异常退出一律不放行；API 进程只留 `%PDF-` 魔数检查。升级后重跑 `pdf_validation_probe.py`，探针必须覆盖结构校验本身，读数写进 E9。
验收：畸形输入被子进程终止 → `UPLOAD_INVALID` 而非 500；正常 PDF 通过；子进程超时不放行；现有抽取隔离不变。实施票据 [E8](../exec/E08-pypdf-upgrade.md)、[E9](../exec/E09-pdf-validation-isolation.md)。
