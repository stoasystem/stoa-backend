# 研究：后端课程数据现状——前置关系、可推导的掌握度、多学科点数规模

- 工单：stoasystem/stoa-frontend#8（父工单 #3「知识星球」学生首页）
- 日期：2026-09-27
- 范围：只读 `stoa-backend` 源码（commit `93787d66`），未查询线上 DynamoDB，未跑迁移。
  所有行号以该 commit 为准。凡涉及线上表里实际有什么数据的地方，都标注了「需线上核实」。

星球的需求回顾：每个知识点是一个点，前置关系是边，每个学生对每个点有五种状态
（点亮 / 进行中 / 下一步 / 可开始 / 锁定），知识点内含技能点，一个学科一个星球，预期超过 200 个点。

---

## 结论速览

| 问题 | 一句话答案 |
|---|---|
| 1. 数据模型 / 前置关系 | 单表 DynamoDB，`PK=PRACTICE` 下五层前缀；**没有任何前置关系被写入或计算**。`prerequisite_lesson_ids` 只是一个永远为空的输出字段。roadmap 只有 completed / current / available，从不产生 locked。 |
| 2. 掌握度来源 | 逐 lesson 的二元「完成」+ 逐 challenge 的原始 attempt 行（含 correct、topic_id、lesson_id）+ 逐 challenge 的 FSRS 复习卡（stability / difficulty / lapses）。**逐 topic 的正确率或熟练度没有任何地方计算或暴露**，但可以从 `ATTEMPTS#` 和 `REVIEW#` 行推出来。 |
| 3. 管理端课程台 | 只做 lesson 级（lesson + exercises 打包）的 draft → review → publish；没有 topic / unit / subject 的写入口。`prerequisites` 键可以经 PATCH 透传存下来，但键名与读取端不一致、无校验、无引用检查。 |
| 4. 规模 | 仓库里只有一份种子：**1 个学科（mathematics）× 1 个年级 × 5 topic × 10 unit × 20 lesson × 60 challenge**；`skills` 全空，去重技能数 = 0。physics / german / english 只有名字没有内容。四语只覆盖 36 个导航标题（en/fr/it 各 36），描述、题干、讲解全是德语。 |
| 5. 教师指派 | 有：`learning_assignment` 实体 + `/adaptive/assignments` 全套路由（teacher/admin 创建，学生 start/complete/skip）。粒度是单个 exercise 或 AI 草稿，**不能指派一个 lesson 或 topic**。 |

---

## 1. 课程数据模型与存储

### 1.1 存储布局

- 单表 DynamoDB，表名来自 `settings.dynamodb_table_name`（`src/stoa/db/dynamodb.py:29-32`）。
- 课程内容全部在一个分区 `PK=PRACTICE` 下，用 SK 前缀区分层级（`src/stoa/routers/practice.py:1-6` 文档字符串；`src/stoa/db/repositories/practice_repo.py:347-469`）：

  | 层级 | SK | 读取函数 |
  |---|---|---|
  | subject | `SUBJECT#{subject_id}` | `get_subjects` L347-352 |
  | topic | `TOPIC#{topic_id}` | `get_topics` L355-363、`get_topic` L366-369 |
  | unit | `UNIT#{unit_id}` | `get_units` L463-469 |
  | lesson | `LESSON#{lesson_id}` | `get_lessons` L372-382、`get_lesson` L385-388 |
  | challenge / exercise | `CHALLENGE#{lesson_id}#{challenge_id}` | `get_challenges` L391-399、`get_all_challenges` L402-417 |

- challenge 另有一份答案无关的指针行 `PK=PRACTICE_CHALLENGE_LOOKUP, SK=CHALLENGE#{challenge_id}`，
  用于按不透明 ID 反查（`practice_repo.py:17-36, 280-291, 420-460`）。每个 challenge 带内容哈希
  `challenge_version = sha256:…`（L255-277）。
- **没有为课程内容建任何 GSI**。仓库里出现的索引只有 `GSI-StudentId`、`GSI-Email`、`GSI-ParentId`、
  教师申请的 review-state 索引（grep `IndexName`）。`get_topics(subject_id)`、`get_lessons(topic_id, unit_id)`、
  `get_units(topic_id)` 都是先 `begins_with` 拉整个前缀再在内存里过滤（L361-362, 378-381, 469）。
  60 条数据无所谓；到 200+ 点 × 若干题时，每个请求（`/overview`、roadmap、catalog）仍会把整棵树拉一遍。

### 1.2 字段（以种子脚本为准，`scripts/seed_practice.py`）

| 实体 | 字段 | 出处 |
|---|---|---|
| subject | `subject_id, name, description, grade_levels[{id,label,order}], accent, order` | L29-41 |
| topic | `topic_id, subject_id, grade_level, title, description, order, status="available"` | L196-200（其余 4 个 topic 同构：L325-329, 450-454, 575-579, 700-704） |
| unit | `unit_id, topic_id, subject_id, grade_level, title, description, order` | L85-94 |
| lesson | `lesson_id, unit_id, topic_id, subject_id, grade_level, topic_title, title, difficulty(intro/practice/review), estimated_minutes, order, challenge_count` | L96-113 |
| challenge | `challenge_id, lesson_id, unit_id, topic_id, subject_id, grade_level, topic_title, order, type(multiple_choice/text_input), prompt, options?, correct_answer, directional_hint_template_id, explanation, correct_feedback, incorrect_feedback` + 写入时加 `challenge_version, challenge_content_hash, hint_non_derivability_decision` | L45-74, L726-749 |

管理端发布的 lesson 投影会额外写 `status="active", rollout_state="active", version_id, manifest_id`
到同一个 `PRACTICE / LESSON#` 与 `CHALLENGE#` 行（`src/stoa/db/repositories/curriculum_ops_repo.py:243-283`）。

对外契约（学生可见、无答案）在 `src/stoa/models/practice.py`：
`PracticeLessonPreview` L44-57、`PracticeExercisePreview` L60-74（含 `skills: list[str]`）、
`CurriculumLessonPreview` L77-96（含 `prerequisite_lesson_ids`、`next_step`）。

### 1.3 `order` / `gradeLevel` / `rolloutState` 的实际用法

- **`order`** 是唯一的顺序机制，每一层都按它排序：
  subject `practice.py:394, 443`；topic L458；lesson L436, 474, 647, 726, 776, 815；unit L642, 735；
  catalog `src/stoa/services/curriculum_service.py:34, 41, 46, 51, 95`。
  注意 `/practice/overview` 的 `recommendedLesson` 按 `(topic_id 字符串, order)` 排（`practice.py:474-477`），
  即 `brueche < geometrie < gleichungen < prozentrechnung < textaufgaben`，**不是** topic 的 `order`（1..5）。
- **`gradeLevel`**：subject 上是对象数组 `grade_levels`，其余层是字符串 `grade_level`。
  只在 catalog 里做过滤（`curriculum_service.py:312-316 _grade_matches`），其余地方原样回传。不参与进度或解锁。
- **`rolloutState`**：由 `_content_state` 推导：`rollout_state or content_state or status or "active"`
  （`curriculum_service.py:330-331`）。学生只能看 `VISIBLE_STATES = {"active"}`（L20）；
  teacher/admin 可 `includePreview`（`practice.py:370-373`，`curriculum_service.py:212-213`）。
  前端类型 `CurriculumRolloutState = seed|draft|reviewed|active|archived`（`stoa-frontend/src/types/practice.ts:224`）
  来自 `.planning/milestones/v3.8-phases/120-.../120-CURRICULUM-ROLLOUT-CONTRACT.md:20-26`，后端并未枚举校验。

  **疑似缺陷（需线上核实）**：种子 topic 写的是 `status: "available"`（seed L199 等 5 处），经 `_content_state`
  得到 `"available"`，不在 `{"active"}` 内，于是 `/practice/curriculum/catalog` 对学生会过滤掉全部 5 个 topic；
  units 是从过滤后的 topics 派生的（`curriculum_service.py:216-220 _all_units`），也会为空。
  lessons、subject 没有 `status`，默认 `"active"`，不受影响。`/practice/overview` 与 roadmap 不做状态过滤，所以不受影响。
  测试夹具用的是 `status: "active"`（`tests/test_curriculum_rollout.py:38-55`），没有覆盖种子的写法。

### 1.4 前置关系：不存在

- `prerequisite_lesson_ids` 只出现在输出模型（`models/practice.py:92-94`）和投影
  `raw.get("prerequisite_lesson_ids", [])`（`src/stoa/services/practice_projection_service.py:193`）。
- **没有任何写入方**：种子 20 个 lesson 都没有此字段（见 1.2 字段表）；管理端建草稿的 `_lesson_payload`
  白名单也没有它（`src/stoa/services/curriculum_ops_service.py:366-379`）。
- `LESSON_FIELD_ALIASES` 里有 `"prerequisites": "prerequisites"`（`curriculum_ops_service.py:54`），
  只在 PATCH 草稿时透传（`_patch_lesson` L496-506），落库键是 `prerequisites`，
  与读取端的 `prerequisite_lesson_ids` **不是同一个键**；校验 `_validation_issues`（L565-587）不看它。
- topic / unit 层完全没有任何关系字段。
- 契约来源：`120-CURRICULUM-ROLLOUT-CONTRACT.md:45` 把 `prerequisite_lesson_ids` 列为 lesson 最小字段；
  `176-RICH-CURRICULUM-EDITOR-MIGRATION-CONTRACT.md:22` 把 `prerequisites` 列为 exercise block 字段。两者都停在契约层。

### 1.5 roadmap 的 locked / available 是怎么算的

不算。`_lesson_status`（`practice.py:313-319`）：

```python
if lesson_id in completed_ids: return "completed"
if lesson_id == current_id:    return "current"
return "available"
```

- `current_id` = 该 topic 内按 `(unit_id, order)` 排序后第一个未完成的 lesson（L645-652；`/path` L724-731；
  `/lessons/{id}` L774-781）。
- unit 的 `status` 硬编码 `"available"`（L354）；topic 的 `status` 硬编码 `"available"`（L467）。
- 前端 `RoadmapLessonStatus` 含 `'locked' | 'review'`、`unlockCondition`（`practice.ts:19, 52`），
  `PracticeRoadmap.tsx:21` 与 `RoadmapLessonNode.tsx:31,93,110` 有 locked 分支，但后端从不发出这两个值。
- 一个 topic 内的进度百分比 = 已完成 lesson 数 / lesson 总数（L432-434, 653）；subject 进度 = 各 topic 百分比平均（L449-453）。

**对星球的含义**：五态里「点亮」可以映射到 completed，「进行中」可以映射到 current，
「下一步 / 可开始 / 锁定」三者都需要边，后端目前一条边都没有。

---

## 2. 掌握度可从哪些事实推导

### 2.1 `get_progress_summary`（`curriculum_service.py:183-209`，路由 `/practice/curriculum/progress` L615-622）

| 字段 | 来源 | 粒度 |
|---|---|---|
| `completedLessons` / `completedLessonIds` | `PROGRESS#{student} / LESSON#{lesson_id}` 行，`status="completed"`（`practice_repo.get_progress` L475-486；写入 `mark_lesson_completed` L489-533，行含 lesson/topic/unit/subject id + `completed_at`） | **逐 lesson，二元**。`POST /practice/lessons/{id}/complete`（`practice.py:790-832`）不看答题结果，点了就算完成。 |
| `mistakeCount` / `weakTopics` | `get_mistakes` = 错误 attempt + 遗留 `MISTAKES#` 行（L662-679）；按 `topic_id` 计数取前 5（`curriculum_service.py:195, 204-207`） | 逐 topic 的**错题数**，没有分母。`/overview` 的版本取前 3，且 subject 硬编码 `"mathematics"`（`practice.py:507-525`）。 |
| `studyStreak` / `practisedToday` | `completed_days` + `ACTIVITY#{student} / DAY#` 行（L102-118, 148-180；`record_study_day` `practice_repo.py:828-874`） | 逐天，与知识点无关。 |

### 2.2 attempt 行：最细的原始事实

`put_attempt`（`practice_repo.py:536-615`）对每次作答写一行不可变记录
`ATTEMPTS#{student} / ATTEMPT#{uuid}`，字段含 `challenge_id, subject_id, topic_id, lesson_id, unit_id, correct, created_at, challenge_version`。
`list_student_attempts(student_id, correct=None)`（L625-636）能拉全量。

→ **逐 challenge / lesson / unit / topic 的正确率都可以从这里算**，只是今天没有任何 service 算，也没有任何路由暴露。
仓库里 grep `mastery|proficiency|accuracy|correct_rate` 没有命中任何实现。

### 2.3 间隔复习（FSRS）：最接近「熟练度」的东西

- 每次作答都会更新一张卡 `REVIEW#{student} / CARD#{challenge_id}`
  （`src/stoa/services/review_service.py:28-79`；`src/stoa/db/repositories/review_repo.py:84-113`），
  字段：`stability, difficulty, due_at, last_reviewed_at, reps, lapses` + `lesson_id, subject_id, topic_id`。
- 调度器 `src/stoa/services/review_scheduler.py`：FSRS-5 权重（L20-24）；`retrievability(state, now)`（L63-69）
  给出当前回忆概率；评分只有 GOOD / AGAIN（`grade_for_answer` L195-197）。
- 路由只有 `/practice/review/due` 与 `/practice/review/summary`（`practice.py:993-1006`），
  返回 dueCount / scheduledCount，**没有按 topic 聚合**。
- 星球可用的推导：某 topic 的熟练度 = 该 topic 各卡 `retrievability` 的均值（或 stability 的分布）；
  卡上已经带 `topic_id`，聚合是纯读取，无需新写入。

### 2.4 其他相关但不够格的信号

- 课程质量分析（`src/stoa/services/curriculum_analytics_service.py:26-69`）：每次作答 / 错答 / 完成
  写 `practice_attempt / wrong_answer / lesson_completed` 信号，聚合到
  `CURRICULUM_METRIC#{content_type}#{public_id}`（`curriculum_analytics_repo.py:154-155`）。
  **跨学生聚合**，用于运营看板，不是个人掌握度。
- 自适应学习记忆快照（`src/stoa/services/adaptive_learning_service.py:1299-1366`）：
  `LEARNING_MEMORY#{student} / SUBJECT#{s}#TOPIC#{t}`（`adaptive_learning_repo.py:244-245`），
  有 `mastered_concepts / struggling_concepts`。「mastered」的定义是 AI 问答的学生反馈均分 ≥ 4 且提问 ≤ 2 次（L1349），
  与练习正确率无关。而且 `topic_id` 来自 AI 回答的 `knowledge_points` 经 `normalize_topic_id` 的 slug
  （`src/stoa/services/learning_profile_service.py:254-257`），是**另一个 ID 空间**
  （例如 AI 标签「Bruchrechnung」→ `bruchrechnung`，课程 topic 是 `brueche`）。
- `learning_profile_service.build_learning_profile`（L109-206）：weakTopics = 问答 topic seeds + 错题 topic 计数，前 10；`strengthTopics` 恒为 `[]`（L192）。

### 2.5 小结：星球五态今天能拿到什么

| 状态 | 今天可直接用的事实 | 缺什么 |
|---|---|---|
| 点亮 | `completedLessonIds`（lesson 级）；topic 级可定义为 topic 内 lesson 全完成 | 完成 ≠ 掌握；需要引入正确率或 retrievability 阈值 |
| 进行中 | roadmap `current` / topic 内有部分 lesson 完成 / `REVIEW#` 有卡但未达阈值 | 无 topic 级聚合端点 |
| 下一步 / 可开始 / 锁定 | 无 | 前置边 |
| 技能点 | 无（`skills` 全空，见 §4） | 技能词表 + 题目打标 |

---

## 3. 管理端课程台能否维护前置关系

### 3.1 现状

- 路由（`src/stoa/routers/admin.py`）：worklist L1212、POST drafts L1279、PATCH draft L1367、
  validation-preview L1381、submit-review L1394、approve L1407、request-changes L1420、
  publish L1434、rollback L1451、archive L1468、preview / diff / audit L1331-1364、migrations dry-run / apply / read L1289-1328。
- 唯一的内容类型是 `lesson_bundle`（lesson + exercises 一起版本化，`curriculum_ops_service.py:101-113`）。
  **没有 subject / topic / unit 的创建或编辑入口**；这三层只能靠种子脚本或直接写表。
- 能力位：`curriculum_author / curriculum_reviewer / curriculum_publisher / migration_operator`（L16-25）。
- 请求模型 `CurriculumLessonDraftRequest`（`admin.py:948-962`）没有前置字段，但 `extra="allow"`（L949）。
  创建时 `_lesson_payload` 白名单（`curriculum_ops_service.py:366-379`）会丢掉多余键；
  PATCH 时 `_patch_lesson` 用 `LESSON_FIELD_ALIASES`（含 `prerequisites`，L54）透传，落到版本文档的 `lesson.prerequisites`。
- 发布投影把整个 lesson dict 写进 `PRACTICE / LESSON#`（`curriculum_ops_repo.py:246-256`），
  所以 `prerequisites` 键会到达学生读取的行，但读取端找的是 `prerequisite_lesson_ids`（§1.4）。
- 校验（L565-587）只查必填字段；不检查引用是否存在、不查环。diff（L599-627）会把它当普通键显示。
- 迁移清单 `curriculum_migration_service.py` 按 lesson 行处理，契约提到「dependency order」（176 契约 L32）但代码没有依赖字段。

### 3.2 最小增补（不改架构）

1. lesson 级边：
   - `CurriculumLessonDraftRequest` 加 `prerequisite_lesson_ids: list[str] = []`（alias `prerequisiteLessonIds`）；
   - `_lesson_payload` 加同名键；`LESSON_FIELD_ALIASES` 加 `prerequisiteLessonIds → prerequisite_lesson_ids`，
     并把现有 `prerequisites` 别名也指向它；
   - `_validation_issues` 在 `publish` 级校验：每个 id 在 `PRACTICE / LESSON#` 存在、不自引用、同 topic 内无环；
   - catalog `_build_lesson`（`curriculum_service.py:271-286`）回传该字段（目前只有 lesson 详情回传）。
2. topic 级边（星球真正需要的）：`TOPIC#` 行加 `prerequisite_topic_ids: list[str]`。
   因为没有 topic 写入口，最短路径是（a）扩展种子脚本；或（b）给迁移清单加 `topics` 段并在 `apply` 时写 `TOPIC#` 行；
   长期需要 `POST/PATCH /admin/curriculum/topics`。
3. 读取侧：`get_roadmap` / `get_overview` 用边 + `completed_ids` 派生 locked / next；这是纯函数，可先在前端或一个新的
   `/practice/curriculum/graph` 端点里做。

---

## 4. 规模

### 4.1 仓库内的 active 课程（`scripts/seed_practice.py`，用脚本实际计数）

| 学科 | 年级 | topic | unit | lesson | challenge | challenge 类型 | lesson 难度 | 去重 skills |
|---|---|---|---|---|---|---|---|---|
| mathematics（ZAP Langgymnasium Zürich） | grade_6_primary（1 个） | 5 | 10 | 20 | 60 | 39 text_input / 21 multiple_choice | 5 intro / 9 practice / 6 review | **0** |
| physics | — | 0 | 0 | 0 | 0 | | | |
| german | — | 0 | 0 | 0 | 0 | | | |
| english | — | 0 | 0 | 0 | 0 | | | |

- 5 个 topic：brueche、gleichungen、geometrie、prozentrechnung、textaufgaben；结构严格 2 unit × 2 lesson × 3 challenge（seed 文档字符串 L6-14）。
- `skills` 字段：60 道种子题**都没有**（字段列表见 §1.2）；只有管理端录入的题会带 `skills`
  （`admin.py:945`，`curriculum_ops_service.py:404`），自由字符串，无词表、无校验。
- `SUPPORTED_SUBJECTS = {math, physics, german, english}`（`curriculum_service.py:19`）；
  `learning_profile_service.py:13-34` 把后三者标为 `foundation`，只有 prompt 文案，没有内容。
  catalog 的 `rolloutSubjects` 不管有没有内容都列出 4 个（L60）。
- ID 不一致：种子用 `mathematics`，catalog 归一化为 `math`（`_normal_subject_id` L343-346）；
  `/overview` weakTopics 硬编码 `"mathematics"`；测试夹具用 `math`。
- **线上表可能比仓库多**：管理端发布过的 lesson 不会回到仓库。需线上核实（`PRACTICE` 分区计数）。

### 4.2 星球点数估算

| 点的定义 | 数学星球今天的点数 | 备注 |
|---|---|---|
| topic = 点 | 5 | 边 0 |
| lesson = 点 | 20 | 边 0 |
| topic + skill 点 | 5 + 0 | 无技能词表 |

距「> 200 点」差一个数量级以上，且其他三个星球是空的。这不是数据模型问题，是内容问题；模型本身不限制层数或数量。

### 4.3 四语内容

- 只翻译导航标题：`src/stoa/services/curriculum_translations.py` 的 `TITLE_TRANSLATIONS`
  有 36 个键（1 subject + 5 topic + 10 unit + 20 lesson），en / fr / it 各 36 条，**对种子内容是齐的**。
- 不翻译：subject / topic / unit 的 `description`（`practice.py:398, 447, 464, 677` 原样回传）、题干、选项、讲解、反馈
  （文档字符串 L3-7 说明这是有意的，ZAP 考试是德语）。
- 翻译按内容 id 硬编码在 Python 里，`translated_title` 缺失时回落德语（L156-160）。
  管理端新发布的 lesson 没有翻译通道；lesson 版本文档有 `language` / `locale_metadata` 字段
  （`curriculum_ops_service.py:45-46, 55-56, 378`）但渲染端不用。
- 到 200+ 点时，翻译需要从代码搬到数据（行内 `title_i18n` 或独立 `TRANSLATION#` 行）。

---

## 5. 教师指派实体

### 5.1 存在：`learning_assignment`

- 实体常量 `ASSIGNMENT_ENTITY = "learning_assignment"`（`src/stoa/db/repositories/adaptive_learning_repo.py:16`）；
  键 `PK=ASSIGNMENT#{assignment_id}, SK=META`（L289-290）。
  按学生列出走 **全表 scan + FilterExpression**（`list_assignments` L406-424），没有 GSI。
- 路由 `src/stoa/routers/adaptive.py`：

  | 路由 | 行 | 谁 |
  |---|---|---|
  | `POST /adaptive/assignments` | L451 | teacher / admin（`_ASSIGNMENT_OPERATOR_UPDATE` L134-137；`_authorized_assignment_create` L279 用它） |
  | `GET /adaptive/assignments/{id}` | L470 | student / parent / teacher / admin |
  | `POST …/start` `…/complete` `…/skip` | L483-531 | student |
  | `POST …/archive` | L533 | teacher / admin |
  | `GET /adaptive/students/me/assignments` | L330 | student |
  | `GET /adaptive/students/{id}/assignments` | L398 | teacher / admin / parent |
  | `GET /adaptive/students/{id}/recommendations` | L375 | teacher / admin |
  | `POST …/assignment-automation/batches/preview|execute` | L415, L432 | teacher / admin |

  路由清单：`docs/security/route-authorization-inventory.json:2237-2249`。
  前端已消费：`stoa-frontend/src/services/learning/learningOperationsApi.ts:50, 57`。
- 记录字段（`adaptive_learning_service.py:220-250`）：`assignment_id, student_id, status, source_type, source_id, title, subject,
  topic_ids, lesson_id, exercise_id, items, answer_key, rationale, created_by, created_by_role, reviewed, due_at, note,
  student_answer, completion_result` + 各状态时间戳。
- 状态机：`draft | recommended | assigned | started | completed | skipped | archived`（L31）；可创建的初始态 L32。

### 5.2 粒度限制

- `_assignment_source`（L1404-1418）：`source_type` 只接受 `curriculum_exercise`（解析**单个** challenge）和 `ai_draft`；
  自动化还会产生 `memory_snapshot` / `curriculum_topic`（L37），但 `curriculum_topic` 只出现在「继续练习」候选里（L1665-1675），
  不是教师可选的来源。
- **不能指派一个 lesson 或一个 topic**。星球的「老师推荐这个点」需要 `source_type = curriculum_lesson | curriculum_topic`
  并把 `lesson_id` / `topic_ids` 填上——记录字段已经有位置，只差来源解析器和校验。
- 推荐引擎 `_next_practice_recommendations`（L1465-1492）：从 weakTopics 出发，每个 topic 最多挑 2 道 active 题
  （`_curriculum_exercise_candidates` L1598-1621），全部带 `teacher_review_required`。
- 归档 lesson 会被活跃 assignment 阻止（`curriculum_ops_service.py:336-350`，`list_active_assignment_refs` 也是 scan）。

---

## 6. 缺口清单（按对星球的阻塞程度排序）

1. **前置边不存在**（topic 与 lesson 两级都没有）。`prerequisite_lesson_ids` 是只读空字段；管理端 `prerequisites` 透传键名不匹配、无校验。→ §1.4, §3
2. **没有 locked / next 的计算**。roadmap 只有 completed / current / available，unit 与 topic 状态硬编码 `available`。→ §1.5
3. **没有逐 topic 的正确率或熟练度**。原始事实齐全（`ATTEMPTS#` 每题 correct + topic_id；`REVIEW#` 每题 FSRS 状态 + topic_id），缺一个聚合函数和一个端点。→ §2.2, §2.3
4. **「完成」不等于「掌握」**：`POST /lessons/{id}/complete` 不看答题结果。→ §2.1
5. **技能点为零**：种子无 `skills`，无技能词表，无校验。→ §4.1
6. **规模**：1 学科 / 5 topic / 20 lesson / 60 题；其余 3 学科无内容；距 200+ 点差一个数量级。→ §4.2
7. **topic / unit / subject 没有写入口**，只能改种子脚本或直接写表；星球的边如果放在 topic 层，今天无法通过管理端维护。→ §3.1
8. **翻译在代码里、只覆盖标题**：新内容无翻译通道；描述与题目只有德语。→ §4.3
9. **疑似缺陷**：种子 topic `status="available"` 会让 `/practice/curriculum/catalog` 对学生返回 0 个 topic / unit（需线上核实）。→ §1.3
10. **ID 空间不一致**：`mathematics` vs `math`；自适应记忆的 topic id 是 AI 标签 slug，不是课程 topic id。星球若要合并「问答弱点」与「练习弱点」需要映射表。→ §2.4, §4.1
11. **教师指派粒度只到单题**，不能指派 lesson / topic。→ §5.2
12. **访问模式**：课程读取每次拉整个 `PRACTICE` 分区再内存过滤；assignments 与 worklist 走 scan。200+ 点 × 题目后应加缓存或按 topic 分键。→ §1.1, §5.1
13. 小问题：`/overview` 的 recommendedLesson 按 topic_id 字母序而非 topic `order`；`/overview` weakTopics 硬编码 subject。→ §1.3, §2.1

### 给星球的最小后端增量（供 #9 参考）

- 数据：`TOPIC#` 行加 `prerequisite_topic_ids`（先由种子/迁移写入）；`CHALLENGE#` 行填 `skills`，并定一个 per-subject 技能词表。
- 读取：新增 `GET /practice/curriculum/graph?subjectId=`，返回 nodes（topic + skills）、edges、以及每个 topic 的
  `{completedLessons, totalLessons, attempts, correct, meanRetrievability}`；五态在前端或该端点内由边 + 这些数字派生。
- 指派：`source_type` 增加 `curriculum_topic` / `curriculum_lesson` 的教师来源解析。

---

## English summary

Scope: read-only review of `stoa-backend` at `93787d66`; the live DynamoDB table was not queried.

1. **Data model.** Single-table DynamoDB; all curriculum rows live under `PK=PRACTICE` with SK prefixes
   `SUBJECT# / TOPIC# / UNIT# / LESSON# / CHALLENGE#{lesson}#{id}` (`practice_repo.py:347-469`), no GSI for content.
   `order` is the only sequencing field; `gradeLevel` is a catalog filter only; `rolloutState` is derived from
   `rollout_state|content_state|status` with students seeing only `"active"` (`curriculum_service.py:20, 330-331`).
   **No prerequisite relation exists anywhere.** `prerequisite_lesson_ids` is an output-only field that nothing writes
   (`models/practice.py:92`, `practice_projection_service.py:193`). Roadmap status is `completed | current | available`
   only (`practice.py:313-319`); `locked` is never emitted, unit/topic status is hard-coded `"available"`.
   Likely bug: seeded topics carry `status: "available"`, which the catalog treats as non-active and filters out (verify live).
2. **Mastery facts.** Per-lesson binary completion (`PROGRESS#`), per-challenge immutable attempts with `correct`
   and `topic_id` (`ATTEMPTS#`, `practice_repo.py:536-615`), per-challenge FSRS review cards with stability/difficulty/lapses
   and `topic_id` (`review_repo.py:84-113`, `review_scheduler.py:63-69`). Per-topic accuracy or proficiency is derivable
   but not computed or exposed anywhere. Lesson completion does not depend on answers.
3. **Admin console.** Lesson-bundle only (draft → review → approve → publish/rollback/archive, `admin.py:1212-1476`);
   no topic/unit/subject authoring. A `prerequisites` key can be stored via PATCH (`curriculum_ops_service.py:54, 496-506`)
   but under a different key than the reader expects, with no validation. Minimal fix: add `prerequisite_lesson_ids` to the
   draft model/payload/validation, and `prerequisite_topic_ids` on `TOPIC#` rows via seed or migration manifest.
4. **Size.** Repo seed = 1 subject (mathematics, ZAP grade 6) × 5 topics × 10 units × 20 lessons × 60 challenges
   (39 text_input / 21 multiple_choice); `skills` is empty on all 60 → 0 distinct skills. physics/german/english have no content.
   Translations: 36 title keys, complete for en/fr/it; descriptions, prompts, explanations are German only; translations are
   code-keyed so admin-published content has no i18n path.
5. **Assignments.** `learning_assignment` exists with full routes under `/adaptive/assignments` (teacher/admin create,
   student start/complete/skip; `adaptive.py:451-548`). Granularity is a single curriculum exercise or an AI draft; a lesson
   or topic cannot be assigned yet. Listing is a table scan.

Gaps, in blocking order: no edges; no locked/next computation; no per-topic mastery aggregate; completion ≠ mastery;
no skills; one subject at 5/20/60 scale; no topic authoring; code-keyed title-only translations; the `available`-status
catalog filter bug; two topic-id spaces (curriculum vs AI-label slugs); exercise-only assignments; full-partition reads.
