---
phase: 475-transactional-usage-assignment-and-relationship-consistency
verified: 2026-07-22T02:15:29Z
verified_head: 9e5cb58ba08a84bc5dc77960b80ee33a2b1c63d8
status: gaps_found
score: 8/15 must-haves verified
requirements_score: 4/8 requirements verified
overrides_applied: 0
gaps:
  - truth: "Question submission converges to the original durable result after provider success/local persistence failure, and every replay is ownership- and schema-safe."
    status: failed
    reason: "OCR/AI success is not durably receipted before an unversioned question update; later replay returns the pending row and bypasses strict command and question-owner validation. No production path creates the terminal_failed proof required by compensation."
    artifacts:
      - path: "src/stoa/routers/questions.py"
        issue: "Provider calls and persistence share broad exception blocks; replay trusts fingerprint/question_id and returns the loaded question without owner validation."
      - path: "src/stoa/db/repositories/question_repo.py"
        issue: "Ordinary question updates neither compare nor increment version and do not constrain the prior state."
      - path: "src/stoa/db/repositories/question_submission_repo.py"
        issue: "Terminal reversal consumes terminal_failed proof, but current production code never writes that state/proof."
      - path: "tests/test_phase475_question_replay.py"
        issue: "The principal replay test monkeypatches both admission and persistence, omitting the required failure window."
    missing:
      - "A durable provider-effect intent/result receipt and conditional question+command completion transaction."
      - "One strict replay entry that validates command schema, owner, key, generation, fingerprint, question identity, and loaded question owner."
      - "A production terminal-failure transition and end-to-end compensation test starting from a real route/service failure."
      - "Versioned/state-constrained question updates that cannot overwrite teacher takeover."
  - truth: "Teacher takeover accepts exactly one still-active teacher and cannot be overwritten by concurrent question processing."
    status: failed
    reason: "The takeover transaction checks only the student account fence; teacher deactivation/deletion can race authorization. Ordinary question updates have no version/state CAS and can overwrite teacher_active after the winning claim."
    artifacts:
      - path: "src/stoa/db/repositories/question_repo.py"
        issue: "claim_teacher_takeover has no teacher fence/profile condition; build_question_update_transaction ignores question version."
      - path: "src/stoa/routers/teachers.py"
        issue: "The observed teacher account is not bound into the repository claim."
    missing:
      - "Teacher active-fence plus active teacher PROFILE role/status/version conditions in the same claim transaction."
      - "Expected-state/version CAS for AI, escalation, feedback, reply, resolve, and other question writers."
      - "Barrier tests for teacher deletion/deactivation and AI-completion versus takeover."
  - truth: "Parent/student relationship creation and repair are fenced for both accounts and cannot revive an inactive or revoked relationship."
    status: failed
    reason: "The relationship transaction contains only the student fence. Its existing-row condition ignores status and the update unconditionally sets status=active, so a same-version revoked/inactive pair is treated as non-conflicting and may be reactivated. Repair inherits the same primitive."
    artifacts:
      - path: "src/stoa/db/repositories/user_repo.py"
        issue: "build_parent_binding_transaction has one student ConditionCheck; the relationship condition omits status and the update overwrites it."
      - path: "src/stoa/routers/admin.py"
        issue: "Preview/apply is wired but applies through the incompletely fenced relationship primitive."
    missing:
      - "Parent and student account fences plus active role/status/profile version observations in the same transaction."
      - "Create/replay conditions requiring identical active status; separate authorized, version-incrementing status transitions."
      - "Parent deletion and revoked/inactive replay race tests."
  - truth: "A rate operation replay returns the immutable receipt created when that operation was admitted."
    status: failed
    reason: "The operation row omits counter_value_after/limit/expiry receipt fields. Replay reads the current shared counter, so operation A changes from counterValue=1 to 2 after operation B is admitted."
    artifacts:
      - path: "src/stoa/services/rate_limit.py"
        issue: "_classify_operation projects current counter state rather than an operation-owned stored receipt."
      - path: "tests/test_phase475_rate_limit.py"
        issue: "No A-then-B-then-replay-A stability assertion exists."
    missing:
      - "Persist counter_value_after, limit, and expiry snapshot on the operation row in the admission transaction."
      - "Replay only the operation-owned receipt and add the missing interleaving regression."
  - truth: "Deletion discovery finds and scrubs cross-account parent, teacher, and actor identities introduced by core relationship and learning writes."
    status: failed
    reason: "_targets_user does not inspect parent_id, teacher_id, or actor_id, so rows owned by another account can be absent from the deletion branch input even though later scrub logic knows some of these fields."
    artifacts:
      - path: "src/stoa/db/repositories/account_deletion_repo.py"
        issue: "Generic discovery omits parent_id/teacher_id/actor_id and has no explicit reverse-index inventory for these identities."
    missing:
      - "Explicit reverse indexes or a closed discovery inventory for cross-account identities."
      - "Deletion tests covering formal relationship rows, teacher sessions/questions, and notification actor metadata through two clean epochs."
  - truth: "Phase 475 evidence fails closed on tool/source-snapshot failure and proves the actual persistence boundaries claimed by its coverage map."
    status: partial
    reason: "Publication ancestry/blob binding and NOT RUN labels are valid, but targeted mypy reports PASS with tool_exit_code=1, source snapshot silently skips unreadable/deleted paths, and key route replay evidence mocks away admission and persistence."
    artifacts:
      - path: "scripts/verify_phase475.py"
        issue: "targeted_mypy ignores nonzero tool completion when no changed-line diagnostic parses; _source_snapshot silently continues on git-show failure."
      - path: "docs/security/phase-475-evidence-results.json"
        issue: "The checked receipt records mypy status PASS while tool_exit_code is 1."
      - path: "tests/test_phase475_question_replay.py"
        issue: "Coverage-mapped replay node replaces both repository transaction and question persistence."
    missing:
      - "Fail-closed mypy exit/summary parsing and exhaustive diff-to-source-snapshot equality."
      - "Lower-boundary provider-success/persistence-failure and replay-integrity nodes in the closed coverage registry."
deferred:
  - truth: "Live AWS DynamoDB behavior"
    addressed_in: "Phase 479"
    evidence: "Phase 475 checked evidence labels LIVE-AWS-DYNAMODB as exact NOT RUN with owner phase 479."
  - truth: "Live provider effects and deployment/production smoke"
    addressed_in: "Phase 480"
    evidence: "Phase 475 checked evidence labels LIVE-PROVIDER-EFFECTS and DEPLOYMENT-AND-PRODUCTION-SMOKE as exact NOT RUN with owner phase 480."
---

# Phase 475：事务用量、分配与关系一致性验证报告

**Phase Goal:** Make the core learning and relationship writes converge under partial failure, retry, and concurrency.
**Verified:** 2026-07-22T02:15:29Z
**Status:** gaps_found
**Re-verification:** 否——首次独立验证

## 结论

Phase 475 的低层事务原语有实质实现，89 个 Phase 475 定向测试和 25 个证据验证器测试在当前源码上均通过；证据 publication 的祖先与 Git blob 绑定也有效。但阶段目标仍未达成。当前生产调用链中存在可观察的不可收敛窗口、跨账户 TOCTOU、失效关系复活、跨学生回放、回放收据漂移和删除发现遗漏。

`475-REVIEW.md` 的 10 个 blocker 与 4 个 warning 经独立检查全部得到确认，没有一项被当前源码反驳。SUMMARY 的完成声明及已发布 PASS 覆盖图因此不能作为阶段通过证据。

## Goal Achievement

### 合并后的 Observable Truths

ROADMAP 的 5 条 success criteria 与 13 份 PLAN frontmatter 合并、去重后得到以下 15 条可观察真值。

| # | Truth | Status | 代码证据 |
| ---: | --- | --- | --- |
| 1 | 问题准入原语把命令、配额、ledger、初始问题与附件操作放入一个有上限的事务，同键同 payload 至多准入一次。 | ✓ VERIFIED | `question_submission_repo.py:245-330, 980-1080`；并发/commit-timeout 下界测试通过。 |
| 2 | provider 成功但本地写失败后，同键重试可恢复原始结果；回放严格校验命令完整性、账户 generation、所有权与问题身份。 | ✗ FAILED | `questions.py:324-349, 475-534` 绕过 `_classify_command()`，provider 结果无 durable receipt。直接 spot-check 可返回 `student-B` 的问题给当前回放路径。 |
| 3 | 真实终态失败可从生产状态机到达，并精确一次恢复问题额度/反转 ledger。 | ✗ FAILED | `question_submission_repo.py:627-637` 只消费 `terminal_failed`；全仓只有测试 fixture 写入该状态与 proof。 |
| 4 | 已完成上传的附件在问题额度反转后保持可复用，storage quota 不退款。 | ✓ VERIFIED | 补偿事务明确排除附件；`test_terminal_reversal_is_exact_once_and_attachment_storage_are_unchanged` 通过。 |
| 5 | 教师接管在并发及账户状态变化下只有一个仍活跃的赢家、一个 session，loser 无副作用且不泄露赢家身份。 | ✗ FAILED | 并发唯一赢家/隐私测试通过，但 `question_repo.py:395-459` 只检查学生 fence，教师删除/停用可在授权后竞态成功。 |
| 6 | 赢家的 takeover notification 使用一个确定性 effect identity，失败后可恢复且不重开竞争。 | ✓ VERIFIED | `notification_service.py:748-870` 与 `teachers.py:236-246` 已接线；effect recovery 测试通过。 |
| 7 | 父子正反关系、profile 投影以及父/子账户状态在一个事务中一致提交，且普通 replay 不会复活 revoked/inactive 关系。 | ✗ FAILED | `user_repo.py:433-492` 只有学生 fence；condition 不含 status，update 无条件写 status。 |
| 8 | 历史关系 repair 为纯 preview、版本绑定、冲突不选边、重复 apply 零写，并在双方账户变化时失败关闭。 | ✗ FAILED | preview/apply 分类本身存在且测试通过，但 apply 使用 Truth 7 的单边 fence 原语，父账户删除竞态未封闭。 |
| 9 | 所有共享 profile writer 与隐私 scrub 使用相同 version/CAS，保留不相关字段且 scrub 对敏感字段获胜。 | ✓ VERIFIED | `user_repo.py:264-360`、`account_deletion_repo.py:683-850`；真实 locale-writer/scrub barrier 测试通过。 |
| 10 | chat/hint 只对一次已准入逻辑操作计数一次，拒绝不增量，且 replay 返回稳定原始准入收据。 | ✗ FAILED | cap/不重复计数成立；但 operation row 不存收据。spot-check：A 首次 `counter_value=1`，B 后 replay A 返回 `2`。 |
| 11 | 错误练习答案在明确边界内精确 round-trip，legacy 缺失明确为 unknown，绝不代入正确答案。 | ✓ VERIFIED | `practice_projection_service.py:43-104`、`practice_repo.py:500-526`；相关 9 个节点通过。 |
| 12 | delivery begin 仅在积极证明账户删除时终态取消；claim loss 与依赖失败保持可恢复。 | ✓ VERIFIED | `notification_repo.py:298-550, 1109+`、`notification_service.py:530-565`；失败后健康重试测试通过。 |
| 13 | 相同已完成删除请求回放存储的 deleted receipt，且不重新调度清理。 | ✓ VERIFIED | `account_deletion_service.py:75-124, 342-413`、`auth.py:939-960`、`deps.py:169-200`；真实 endpoint fake 的零 effect 计数通过。 |
| 14 | 证据 coverage 节点真实覆盖声称的事务/持久化边界，并在工具或 source snapshot 异常时失败关闭。 | ✗ FAILED | replay 节点 monkeypatch 仓储；mypy receipt 为 `PASS` 但 `tool_exit_code=1`；snapshot 对 `git show` 失败静默跳过。 |
| 15 | 证据绑定一个干净 source candidate，后续 HEAD 未改变 publication blobs，live AWS/provider/deployment 未被伪称为运行。 | ✓ VERIFIED | candidate `cc709c1`；publication `370562a` 是直接子提交；当前 HEAD `9e5cb58` 为后代且 runtime diff 为空；两个 evidence blob OID 未变；三项外部义务明确 `NOT RUN`。 |

**Score:** 8/15 must-haves verified

### ROADMAP Success Criteria

| # | Roadmap criterion | Status | 判定 |
| ---: | --- | --- | --- |
| 1 | 相同问题重试在任意已测失败点后只有一个问题、一个额度、一个 ledger。 | ✗ FAILED | admission 原子性成立，但 provider 成功/本地提交失败与无键重试未收敛。 |
| 2 | 两个并发 teacher takeover 只有一个 owner/session/notification 与确定性 loser。 | ✗ FAILED | 常规 barrier race 通过；教师账户 TOCTOU 与普通问题写覆盖可破坏最终状态。 |
| 3 | 关系不单边、repair 幂等、真实 profile writer/scrub race 保留数据。 | ✗ FAILED | profile CAS 通过；父账户 fence 缺失与 revoked revival 使整体 criterion 失败。 |
| 4 | 429 不增量；delivery transient failure 可恢复且不误判 deletion。 | ✗ FAILED | delivery 部分通过；rate replay 收据不稳定，未达到完整幂等结果合同。 |
| 5 | 错误答案安全 round-trip；完成删除回放存储 receipt 且零新清理。 | ✓ VERIFIED | 两条行为均由当前实现和定向节点支持。 |

## Requirements Coverage

| Requirement | Source plans | 完整描述 | Status | 实际证据 |
| --- | --- | --- | --- | --- |
| V9DATA-01 | 475-01..03, 13 | Question quota, idempotency, usage ledger, upload consumption, and initial question persistence commit atomically or converge through an explicitly tested recovery state. | ✗ BLOCKED | 准入事务通过；provider 结果持久化失败、回放完整性、终态 proof 生产路径与可选 key 仍失败。 |
| V9DATA-02 | 475-04..05, 13 | Concurrent teacher takeover has exactly one winner, one session, and one notification through a conditional/transactional claim. | ✗ BLOCKED | 常规一赢家通过；教师 fence 缺失，且无版本普通问题更新可覆盖 takeover。 |
| V9DATA-03 | 475-06..07, 13 | Parent/student forward and reverse bindings and required profile changes commit transactionally, and a reconciliation tool repairs historical asymmetry idempotently. | ✗ BLOCKED | 三投影事务/preview 存在；父 fence 与 inactive/revoked 状态条件缺失。 |
| V9DATA-04 | 475-09, 13 | Chat, hint, and related rate-limit counters do not increase after rejection; provider failures and retries follow documented consumption/idempotency semantics. | ✗ BLOCKED | 计数 cap 与 same-op 不增量通过；同一操作的公开准入 receipt 随其他请求漂移。 |
| V9DATA-05 | 475-10, 13 | Incorrect practice attempts persist a bounded, display-safe student answer and return it accurately in mistake review while handling legacy rows as unknown. | ✓ SATISFIED | normalization、dual-field schema、unknown legacy 与 redacted pre-write rejection 均已接线和测试。 |
| V9DATA-06 | 475-08, 13 | Every shared parent-profile writer participates in one version/CAS-and-increment contract, or deletion uses a genuinely narrow non-overwriting update. | ✓ SATISFIED | source registry、窄更新、version increment、真实 writer/scrub 两种顺序均通过。 |
| V9DATA-07 | 475-11, 13 | Delivery-begin distinguishes typed conditional/fence loss from transient dependency failure; only proven deletion terminalizes. | ✓ SATISFIED | ordered cancellation reason + strong fence/intent rere读；healthy retry exactly once。 |
| V9DATA-08 | 475-12, 13 | Identical completed deletion retry returns the stored deleted receipt through the real endpoint without reopening cleanup. | ✓ SATISFIED | nested receipt 严格校验，terminal suppresses background scheduling，identity fallback 可达。 |

没有 Phase 475 orphaned requirement：V9DATA-01..08 都出现在计划 frontmatter；但 `.planning/REQUIREMENTS.md` 顶部 checkbox 与其 traceability 表的 Complete 状态目前互相矛盾，且独立验证不支持 01..04 完成。

## Required Artifacts

| Artifact | L1/L2 | L3/L4 | Status | Details |
| --- | --- | --- | --- | --- |
| `question_submission_repo.py` | 存在且 substantive（1092 行） | admission 已接 Dynamo transaction；terminal producer 缺失 | ⚠ PARTIAL | 原子准入有效，终态 compensation 只完成后半段。 |
| `routers/questions.py` | 存在且 substantive（655 行） | route 已调用 admission/provider；恢复/所有权链断裂 | ✗ HOLLOW RECOVERY | provider 结果未先 durable，replay 绕过严格分类。 |
| `reconcile_question_submissions.py` | 存在且 substantive（152 行） | preview/apply 已接 repo；只接受显式坐标 | ⚠ PARTIAL | 可处理人工播种 terminal proof，但生产无生成/调度路径。 |
| `question_repo.py` | 存在且 substantive（759 行） | takeover transaction 已接；teacher fence/question CAS 缺失 | ⚠ PARTIAL | session 确定性成立，跨 writer 一致性不成立。 |
| `notification_service.py` | 存在且 substantive（1987 行） | takeover effect 与 typed delivery 均已接 | ✓ VERIFIED | effect ID、replay、dependency retry 可达。 |
| `user_repo.py` | 存在且 substantive（1173 行） | binding/profile/repair 已接；单边 fence/status overwrite | ⚠ PARTIAL | profile CAS 部分通过，relationship authority 失败。 |
| `routers/admin.py` | 存在且 substantive | preview/apply route 已接 capability gate | ⚠ PARTIAL | 底层 apply 原语未封闭父账户竞态。 |
| `rate_limit.py` | 存在且 substantive（521 行） | hint 生产路径已接；chat 保留 message-command authority | ⚠ PARTIAL | cap/opaque operation ID 成立，stable receipt 不成立。 |
| `practice_projection_service.py` / `practice_repo.py` | 存在且 substantive | request → normalize → persist → mistake projection 数据流完整 | ✓ VERIFIED | 真实 answer 数据不是 static fallback。 |
| `notification_repo.py` | 存在且 substantive（1543 行） | service 对四种 disposition 有明确分支 | ✓ VERIFIED | dependency 与 deletion 不再混淆。 |
| `account_deletion_service.py` / `deps.py` / `auth.py` | 存在且 substantive | identity fallback → stored receipt → terminal no-schedule 完整 | ✓ VERIFIED | receipt replay 本身稳定。 |
| `verify_phase475.py` | 存在且 substantive（1018 行） | capture/publication 已接 | ⚠ WARNING | mypy 与 snapshot 失败关闭不完整。 |
| Phase 475 tests | 13 个模块，均 substantive | 89/89 当前通过 | ⚠ PARTIAL | 多个核心节点依赖高层 monkeypatch/fake，不能证明缺失的生产边界。 |

## Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| Question route | admission transaction | `admit_question_submission()` | ✓ WIRED | 初始 command/counter/ledger/question/attachment 同事务。 |
| Provider success | durable result/command completion | `update_status()` | ✗ NOT_WIRED | 没有 durable provider receipt 或 command completion transaction。 |
| Replay | strict command + owner validation | preflight `_classify_command()` | ✗ NOT_WIRED | route 自行只比 fingerprint。 |
| Ordinary question writer | takeover version/state | expected version + allowed transition | ✗ NOT_WIRED | condition 仅 row exists + student owner。 |
| Takeover | teacher account lifecycle | teacher fence/profile condition | ✗ NOT_WIRED | 事务只有 student fence。 |
| Takeover winner | notification effect | `ensure_teacher_takeover_notification()` | ✓ WIRED | loser 不进入 effect 分支。 |
| Parent binding | both account lifecycles | parent + student fences | ⚠ PARTIAL | 只有 student fence。 |
| Repair apply | atomic relationship writer | `apply_parent_binding_repair()` | ✓ WIRED | 接线存在，但继承底层缺口。 |
| Rate operation | immutable replay receipt | operation row fields | ✗ NOT_WIRED | operation row无 admission counter snapshot。 |
| Delivery intent | typed begin outcome | repository result → service routing | ✓ WIRED | terminal cancellation 仅 proven deletion。 |
| Deletion endpoint | stored terminal receipt | dependency fallback + `is_terminal` | ✓ WIRED | terminal replay不调度 background task。 |
| Deletion discovery | cross-account identities | `_targets_user()` / reverse inventory | ✗ NOT_WIRED | parent_id/teacher_id/actor_id 均返回 false。 |

## Data-Flow Trace (Level 4)

| Artifact | Data | Source | Produces real/stable data | Status |
| --- | --- | --- | --- | --- |
| Question replay response | question content/result | command.question_id → `get_question()` | 数据真实，但 owner/schema 未验证；provider success 可丢失 | ✗ UNSAFE FLOW |
| Question terminal compensation | terminal proof | command fields | 没有 production writer | ✗ DISCONNECTED |
| Rate replay receipt | counterValue/expiry | 当前全局 counter read | 真实但不是该 operation 的稳定值 | ✗ UNSTABLE |
| Mistake review | `yourAnswer`/`answerState` | persisted attempt fields | 真实 bounded data；legacy 明确 unknown | ✓ FLOWING |
| Delivery begin | disposition | transaction reasons + strong reads | 真实 repository evidence | ✓ FLOWING |
| Deletion replay | `deleted` receipt | persisted nested receipt | 真实且 replay 保持原值 | ✓ FLOWING |

## Behavioral Spot-Checks

| Behavior | Command/Probe | Result | Status |
| --- | --- | --- | --- |
| Phase 475 focused code | 12 个 `test_phase475_*` runtime modules | 89 passed in 1.69s | ✓ PASS |
| Evidence verifier | `pytest -q tests/test_phase475_evidence_verifier.py` | 25 passed | ✓ PASS |
| Publication binding | `python scripts/verify_phase475.py verify-publication` | exit 0 | ✓ PASS |
| Current lint | Ruff over 21 runtime files | All checks passed | ✓ PASS |
| Replay owner fence | 调用 `_project_question_admission()`，command 指向 `student-B` 问题 | 返回了该 foreign question dict | ✗ FAIL |
| Question update CAS | 构造 version=7 的 `build_question_update_transaction()` | condition 仅 `attribute_exists...student_id=:owner`，无 version；update 不增 version | ✗ FAIL |
| Relationship fences/status | 构造 `build_parent_binding_transaction()` | 仅一个 ConditionCheck；row condition 无 status，update 强制 status | ✗ FAIL |
| Revoked relationship replay | `_parent_relationship_conflicts()` 输入同版本 revoked rows | 返回 `False` | ✗ FAIL |
| Rate stable replay | A admitted → B admitted → replay A | counter value `1 → 2` | ✗ FAIL |
| Idempotency privacy | client key `parent@example.com private question` | 原文出现在 command SK | ✗ FAIL |
| Cross-account deletion discovery | `_targets_user()` 分别输入 parent_id/teacher_id/actor_id | 三项均为 `False` | ✗ FAIL |

### Probe Execution

没有 PLAN/SUMMARY 声明 `probe-*.sh`，仓库也没有 Phase 475 conventional shell probe；本项按合同标记为 **SKIPPED (no declared probe)**。`scripts/verify_phase475.py` 的独立 publication 校验已作为 behavioral spot-check 实际执行。

## 475-REVIEW 独立复核

| Finding | 复核 | 当前源码证据 |
| --- | --- | --- |
| CR-01 provider success/local write failure | 🛑 CONFIRMED | `questions.py:475-534`；成功结果未 durable，异常与 provider failure 合并，retry 快路径不重做 effect。 |
| CR-02 replay ownership/integrity bypass | 🛑 CONFIRMED | `questions.py:324-349, 160-178`；直接 spot-check 返回 foreign student row。 |
| CR-03 question update lacks version CAS | 🛑 CONFIRMED | `question_repo.py:588-640`；shape probe 无 version condition/increment。 |
| CR-04 takeover lacks teacher fence | 🛑 CONFIRMED | `question_repo.py:395-459` 只有 student active fence；route observed teacher profile 未传入 claim token。 |
| CR-05 relationship lacks parent fence | 🛑 CONFIRMED | `user_repo.py:460-492` 唯一 ConditionCheck 指向 student。 |
| CR-06 revoked/inactive relationship revival | 🛑 CONFIRMED | row condition 不比 status，update 无条件 SET active；conflict helper 对 revoked 返回 false。 |
| CR-07 terminal compensation unreachable | 🛑 CONFIRMED | `terminal_failed` proof writer只出现在 test fixture，生产 rg 无结果。 |
| CR-08 raw question idempotency key persistence | 🛑 CONFIRMED | raw key进入 command SK/id、ledger SK/event/idempotency field及 job `commandId`。 |
| CR-09 unstable rate replay receipt | 🛑 CONFIRMED | operation row无 receipt；A/B/replay A probe 得到 1→2。 |
| CR-10 cross-account identity discovery omissions | 🛑 CONFIRMED | `_targets_user()` 对 parent_id/teacher_id/actor_id 均为 false。 |
| WR-01 optional question idempotency key | ⚠ CONFIRMED | model 字段 optional；缺省 key 基于本次随机 UUID，lost response 无法重建。 |
| WR-02 mypy false PASS | ⚠ CONFIRMED | checked JSON 同时记录 `status=PASS` 与 `tool_exit_code=1`；代码只看 changed-line parse。 |
| WR-03 incomplete source snapshot | ⚠ CONFIRMED | `_source_snapshot()` 在 `git show` 非零时直接 `continue`。 |
| WR-04 replay test mocks persistence | ⚠ CONFIRMED | `test_phase475_question_replay.py:82-116` monkeypatch command read/admission/question write。 |

## Anti-Patterns Found

Phase 475 runtime inventory未发现未引用的 `TBD`、`FIXME` 或 `XXX` debt marker。`return {}`/空列表命中均是安全默认或测试 fake，不是用户可见 stub。真正的阻塞模式是事务/状态机接线缺口，而不是占位文件。

| File | Pattern | Severity | Impact |
| --- | --- | --- | --- |
| `routers/questions.py` | 外部效果与状态持久化宽泛 try/except；replay 自行降级分类 | 🛑 Blocker | durable provider result 丢失、跨 owner 数据投影。 |
| `question_repo.py` | 普通状态写无 version/state CAS；takeover 无 teacher fence | 🛑 Blocker | 覆盖 winner 或授予已停用教师。 |
| `user_repo.py` | 单边 fence、status 不在条件、无条件 status update | 🛑 Blocker | 已删除父账户残留、inactive relationship revival。 |
| `question_submission_repo.py` / reconciliation job | raw client key 进入 durable coordinates/output；terminal proof 无 producer | 🛑 Blocker | 隐私泄漏与永不补偿。 |
| `rate_limit.py` | replay 使用共享 current counter | 🛑 Blocker | 幂等 response 不稳定。 |
| `account_deletion_repo.py` | generic discovery 漏跨账户 identity fields | 🛑 Blocker | 删除后关系/教师身份残留。 |
| `verify_phase475.py` | 工具退出/source snapshot 不 fail closed | ⚠ Warning | 证据可能在工具失败或路径缺失时继续 PASS。 |
| `test_phase475_question_replay.py` | mock 掉事务与持久化边界 | ⚠ Warning | coverage map 高估真实 recovery 证明。 |

## Deferred Items

以下不是 Phase 475 的可执行 gap，因为 ROADMAP/checked evidence 明确把它们分配给后续阶段：

| Item | Addressed In | Evidence |
| --- | --- | --- |
| Live AWS DynamoDB behavior | Phase 479 | exact `NOT RUN` obligation `LIVE-AWS-DYNAMODB`。 |
| Live provider effects | Phase 480 | exact `NOT RUN` obligation `LIVE-PROVIDER-EFFECTS`。 |
| Deployment/production smoke | Phase 480 | exact `NOT RUN` obligation `DEPLOYMENT-AND-PRODUCTION-SMOKE`。 |

这些 NOT RUN 边界被诚实标注，但不能用于反驳当前本地源码已经可观察的 blocker。

## Human Verification Required

无。此次失败均可由源码、事务 shape、纯函数 probe 或本地测试确定；不需要用主观 UI/人工步骤把 FAILED 降级为 UNCERTAIN。

## Gaps Summary

阶段不能进入下一阶段依赖链。核心问题不是“测试没跑”，而是测试没有覆盖生产上最关键的组合边界：provider effect 与 durable result、question writer 与 takeover、teacher/parent 生命周期与 claim/binding、operation identity 与稳定 receipt、删除分支与跨账户 identity discovery。

建议 gap plan 先按 frontmatter 的六个根因拆分。尤其应先统一问题 command/effect 状态机与 question version CAS，再补 teacher/parent 双边账户 fence；否则继续增加 route-level replay 测试只会重复模拟已知不完整行为。

---

_Verified: 2026-07-22T02:15:29Z_
_Verifier: the agent (gsd-verifier)_
