# STOA 深度回测与 AI 行为复查 — 2026-09-24

## 版本与范围

后端 `main` 从 `f47fe62202f363354883a0ba3308fa50217054d8` fast-forward 到 `5a6ba852cd8f778701c2f99ffe9e54c0c9bbbcbd`，共 17 个远端提交，无本地分叉。原有 `.scratch/`、`CONTEXT.md`、`docs/testing/` 和上一轮审计报告保留。业务源码未修改；没有 commit、push 或部署。

交叉核对的远端固定版本：infra `c0d79df903e74dded11aed340ef7b1a6b741b577`、frontend `830e1b7ea3c3f43697b717eeba84d13a89fb1d83`、docs `007e24530a5ef4f73bac9ea7fb5c64c26629da62`。只读取对应源码文件，不同步或修改其他工作区。远端源码证明配置与调用关系，不证明当前部署版本或线上实际配置。

所有测试使用合成数据、假 AWS 凭据和禁用网络的 pytest；没有真实 Bedrock 推理、线上学生操作、生产日志读取或真实邮件。用户报告的 thinking 过久、语言不匹配和超纲拒答是人工观察；下文明确区分可重复的代码行为与尚未测量的线上模型表现。

## 测试结果

| 测试 | 结果 | 解释 |
| --- | --- | --- |
| 现有仓库广泛回归 | 3608 passed / 32 failed / 5 skipped | 32 项全部是发布测试找不到当前物理后端目录旁的 canonical infra 根目录；不是 32 个业务缺陷 |
| infra 工作流测试收集 | 1 个文件未纳入 | `tests/test_infra_workflow_contract.py` 同样要求物理相邻 infra；已有 infra 在 `/Users/zhdeng/stoa-infra` |
| 历史缺陷适配回放 | 18 passed / 1 expected failure | 唯一仍失败断言为 #7；只适配旧测试的存储契约/返回形状，不修改应用代码 |
| 已修复区域现有测试 | 393 passed | 与广泛回归有重叠，不累加为独立测试数 |
| AI 独立复验 | 11 expected failures / 17 passed | 9 个失败对应四项发布问题，另 2 个为模型 JSON 形状的内部异常观察；不单独发布 |
| 输出独立 command 见证 | 3 passed | 真实 command/AI 服务代码确认截断内容进入完成记录，并验证形状错误被外层捕获；存储与额度写入为本地记录器 |
| PDF 受限子进程 | #6 仍可复现 | 4,194,540 字节合成输入进入真实解析器后，在外部 3 CPU 秒限制下被 SIGXCPU 终止 |

广泛回归命令：

```sh
env -u AWS_PROFILE AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing \
  AWS_SESSION_TOKEN=testing AWS_EC2_METADATA_DISABLED=true \
  AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_CONFIG_FILE=/dev/null \
  .venv/bin/python -m pytest -q --tb=short \
  --ignore=tests/test_infra_workflow_contract.py \
  --junitxml=.scratch/ai-audit-20260924/baseline.xml
```

AI 独立复验沿用同一环境，执行：

```sh
.venv/bin/python -m pytest -q --tb=short \
  .scratch/ai-audit-20260924/latency/test_latency_contracts.py \
  .scratch/ai-audit-20260924/language-grade/test_language_grade.py \
  .scratch/ai-audit-20260924/test_output_contract.py
```

## 四项发现

### AI-01 — 等待预算超出运行时，实际客户端也绕过超时配置

远端 infra 的主 API Lambda 超时为 29 秒。后端在准备工作完成后才开始计算 90 秒 AI deadline，并设置 120 秒 AI lease；stream 路由在完整生成结束后才构造 SSE 响应。实际调用使用的 allowance wrapper 创建 Bedrock client 时没有带上服务直调路径的超时与单次尝试配置；CountTokens 也可能耗尽期限后仍发起生成。

注入时钟的 30 秒完成案例在 29 秒前没有 SSE；10 秒控制案例通过。对真实 `_execute_message_command` 注入 29 秒强制中断后，已经写入学生消息并预留额度，但没有助手答案/result_json，command 留在 `ai_running`、lease 为 120 秒。此测试模拟中断，不测量真实 Bedrock 延迟，也不证明本次人工观察的唯一原因。

### AI-02 — 年级被写成问题准入限制

真实 `get_ai_answer` 组装给模型的系统提示词要求只回答学生当前年级的问题；复杂问题被导向老师介入。这与本次用户明确的产品要求冲突：超出年级的同学科问题，应先用可理解的解释、例子或类比回答。

数学 Grade 6 问导数、物理 Grade 5 问量子物理的捕获测试均确认此提示词。问题本身能到达模型边界，没有发现此路径中的前置年级硬拦截。本轮证明的是提示词契约问题；用户观察到的完整拒答频率没有通过真实模型重测。

### AI-03 — Accept-Language 忽略质量权重

`de;q=0,en;q=1` 被解析为德语，`fr;q=0.2,en;q=1` 被解析为法语。真实 middleware → conversation locale helper → prompt builder 的本地链路确认错误选择会写进输出语言指令。q 权重和 q=0 的语义参见 [RFC 9110 §12.4.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.4.2)。

单一 `de/en/fr/it` 请求全部正确到达 prompt；无请求语言时，profile fallback 也通过。本轮不能把这个多语言请求头缺陷等同于用户当前 UI 中的语言不匹配。提示词已指定语言也不等于真实模型一定遵循；原始问题与当次请求尚未拿到。

### AI-04 — 被截断的 JSON 被接受为成功答案

当 provider 返回 `stop_reason=max_tokens` 和不完整 JSON 时，解析器回退到把原文作为 answer，后续类型校验接受它。buffered 与 stream 两条 provider 路径均可复现，完整答案控制通过。

补充观察：JSON 顶层数组在 service 内引发 AttributeError，但 conversation route 会捕获一般异常并返回既有失败边界；没有把它误报为未经捕获的 HTTP 500，也没有另建 issue。

## 上轮 issue 复查

12 个 CLOSED issue（#2、#4、#5、#8、#9、#11–#17）的原缺陷在本轮覆盖场景均已修复。仍 OPEN 的 #3、#10 也已通过原行为回归；保留原 issue 状态，本轮不代替部署/CI 验收。仍 OPEN 的 #6、#7 继续可复现，沿用已有 issue，避免重复发布。

逐条矩阵、旧测试适配说明、重放命令和证据位于 `.scratch/ai-audit-20260924/prior-issues/REPORT.md`。

## 证据包与发布

本轮日志、JUnit XML、固定远端源码、独立复验、issue 正文及发布回执保存在 `.scratch/ai-audit-20260924/`。`manifest.json` 记录文件哈希；`publication-verified.json` 记录直接 GET 回读后的 issue 标题、正文哈希和链接。该证据包只代表本地审计和 issue 发布，不代表问题已修复或线上验收。

已发布并直接 GET 核对标题、正文和 OPEN 状态：

- AI-01: [#18 — [P1] AI chat waits synchronously for up to 90 seconds inside a 29-second API Lambda](https://github.com/stoasystem/stoa-backend/issues/18)
- AI-02: [#19 — [P1] AI prompt treats the student's grade as an answer eligibility limit instead of adapting advanced concepts](https://github.com/stoasystem/stoa-backend/issues/19)
- AI-03: [#20 — [P2] Accept-Language quality values are discarded, allowing an explicitly excluded response language](https://github.com/stoasystem/stoa-backend/issues/20)
- AI-04: [#21 — [P2] Token-truncated model JSON is accepted as a successful chat answer](https://github.com/stoasystem/stoa-backend/issues/21)
