"""The knowledge base becomes draft lessons in four languages, without its textbook records.

The upstream data here is made up in the shape of cn-math-taxonomy's data/ files
(topics, questions, dependencies); the real data is CC BY-NC 4.0 and stays out of
the repository. A fake translator fills the batches the way docs/
knowledge-base-translation.md asks. The last tests send the manifest through the
real dry run, apply, review and publish against the seeded table double, and read
the published exercise as a French-speaking student.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from scripts import knowledge_base_import as kb
from scripts import seed_practice
from stoa.db.repositories import practice_repo
from stoa.services import (
    answer_judging,
    curriculum_migration_service,
    curriculum_ops_service,
    curriculum_translations,
    exercise_localization,
    knowledge_base_catalog,
    practice_projection_service,
)
from test_curriculum_publish_projection import install_seeded_table


OPERATOR = {
    "sub": "operator-1",
    "role": "admin",
    "capabilities": {
        curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY: "granted",
        curriculum_ops_service.REVIEWER_CAPABILITY: "granted",
        curriculum_ops_service.PUBLISHER_CAPABILITY: "granted",
        curriculum_ops_service.AUTHOR_CAPABILITY: "granted",
    },
}

TOPICS = [
    {
        "id": "cnm_p101", "name": "分数的加法", "domain": "数与代数", "grade": 5, "semester": "下",
        "chapter": "五年级下册 第6单元 分数的加法和减法", "type": "procedural",
        "description": "同分母分数相加，分母不变，分子相加。",
        "mastery_criteria": ["能计算同分母分数加法", "能把结果化简"],
        "diagnostic_question": {"question": "1/4+2/4=?", "answer": "3/4"},
        "external": False, "standards": [{"id": "cms-2022:3.NA.09", "confidence": "exact"}],
        "root_reason": "教材从这里开始。",
    },
    {
        "id": "cnm_p100", "name": "分数的意义", "domain": "数与代数", "grade": 5, "semester": "下",
        "chapter": "五年级下册 第4单元", "type": "conceptual", "description": "把单位1平均分。",
        "mastery_criteria": ["能说出分数的意义"],
        "diagnostic_question": {"question": "?", "answer": "?"},
        "external": False, "standards": [],
    },
    {
        "id": "cnp_h001", "subject": "physics", "name": "力的合成", "domain": "运动和相互作用",
        "grade": 10, "semester": "上", "chapter": "必修第一册 第三章", "type": "conceptual",
        "description": "求两个力的合力。", "mastery_criteria": ["能用平行四边形定则"],
        "diagnostic_question": {"question": "?", "answer": "?"},
        "external": False, "standards": [], "mathLinks": ["cnm_p101"],
    },
]
QUESTIONS = [
    {"id": "cnm_p101_q1", "topicId": "cnm_p101", "difficulty": "basic", "type": "numeric",
     "prompt": "计算：1/4 + 2/4", "answer": "3/4", "explanation": "分母不变，分子相加。", "verify": "x"},
    {"id": "cnm_p101_q2", "topicId": "cnm_p101", "difficulty": "standard", "type": "choice",
     "prompt": "小明吃了 3/8 个蛋糕，小红吃了 2/8 个。一共吃了多少？",
     "choices": [{"key": "A", "text": "5/16"}, {"key": "B", "text": "5/8"}, {"key": "C", "text": "1/8"}],
     "answer": "B", "explanation": "3/8 + 2/8 = 5/8。"},
    {"id": "cnm_p101_q3", "topicId": "cnm_p101", "difficulty": "standard", "type": "numeric",
     "prompt": "写出两个和为 1 的同分母分数（用逗号隔开）。", "answer": "1/2，1/2",
     "explanation": "1/2+1/2=1。", "unordered": True},
    {"id": "cnm_p101_q4", "topicId": "cnm_p101", "difficulty": "basic", "type": "choice",
     "prompt": "看图。", "choices": [{"key": "A", "text": "1"}, {"key": "B", "text": "2"}],
     "answer": "A", "explanation": "看图。", "figure": "<svg/>"},
    {"id": "cnm_p101_q5", "topicId": "cnm_p101", "difficulty": "basic", "type": "self",
     "prompt": "你会了吗？", "answer": "会", "explanation": "自评。"},
    {"id": "cnm_p100_q1", "topicId": "cnm_p100", "difficulty": "basic", "type": "numeric",
     "prompt": "把一个蛋糕平均分成 4 份，1 份是几分之几？", "answer": "1/4", "explanation": "1/4。"},
    {"id": "cnp_h001_q1", "topicId": "cnp_h001", "difficulty": "basic", "type": "numeric",
     "prompt": "3 N 和 4 N 的两个力互相垂直，合力 F合 是多少 N？", "answer": "5",
     "explanation": "按教材约定，用勾股定理：5 N。"},
]
DEPENDENCIES = [
    {"topicId": "cnm_p101", "prerequisiteId": "cnm_p100", "strength": "hard", "reason": "x"},
    {"topicId": "cnp_h001", "prerequisiteId": "cnm_p101", "strength": "soft", "reason": "x"},
]


def _upstream(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    (data / "topics.json").write_text(json.dumps(TOPICS, ensure_ascii=False), encoding="utf-8")
    (data / "questions.json").write_text(json.dumps(QUESTIONS, ensure_ascii=False), encoding="utf-8")
    (data / "dependencies.json").write_text(json.dumps(DEPENDENCIES), encoding="utf-8")
    return data


#: What the fake translator writes per locale, keyed by the new ids.
WORDS = {
    "de": ("Brüche addieren", "Gleichnamige Brüche addieren.", "Bruch verstehen", "Kräfte addieren",
           "Berechne: 1/4 + 2/4", "Noah isst 3/8 eines Kuchens, Mia 2/8. Wie viel essen sie zusammen?",
           "Schreibe zwei gleichnamige Brüche mit der Summe 1 (durch Komma getrennt).",
           "Ein Kuchen wird in 4 gleiche Teile geteilt. Welcher Bruch ist 1 Teil?",
           "Zwei Kräfte von 3 N und 4 N stehen senkrecht. Wie gross ist F_res in N?", "Mehr als 1"),
    "en": ("Adding fractions", "Add fractions with like denominators.", "Understanding fractions",
           "Adding forces", "Calculate: 1/4 + 2/4", "Noah eats 3/8 of a cake, Mia 2/8. How much together?",
           "Write two like fractions that add up to 1 (separated by a comma).",
           "A cake is cut into 4 equal parts. What fraction is 1 part?",
           "Two perpendicular forces of 3 N and 4 N. What is F_net in N?", "More than 1"),
    "fr": ("Additionner des fractions", "Additionner des fractions de même dénominateur.",
           "Comprendre les fractions", "Additionner des forces", "Calcule : 1/4 + 2/4",
           "Noah mange 3/8 d'un gâteau, Mia 2/8. Combien en tout ?",
           "Écris deux fractions de même dénominateur dont la somme vaut 1 (séparées par une virgule).",
           "Un gâteau est coupé en 4 parts égales. Quelle fraction est 1 part ?",
           "Deux forces perpendiculaires de 3 N et 4 N. Que vaut F_res en N ?", "Plus que 1"),
    "it": ("Addizionare frazioni", "Addizionare frazioni con lo stesso denominatore.",
           "Capire le frazioni", "Sommare forze", "Calcola: 1/4 + 2/4",
           "Noah mangia 3/8 di una torta, Mia 2/8. Quanto in tutto?",
           "Scrivi due frazioni con lo stesso denominatore la cui somma è 1 (separate da una virgola).",
           "Una torta è divisa in 4 parti uguali. Che frazione è 1 parte?",
           "Due forze perpendicolari di 3 N e 4 N. Quanto vale F_ris in N?", "Più di 1"),
}


def _translate(batch: dict[str, Any]) -> dict[str, Any]:
    """Fill a batch the way the translation rules ask."""
    points: dict[str, Any] = {}
    exercises: dict[str, Any] = {}
    for locale, w in WORDS.items():
        names = {"kb-m-p101": (w[0], w[1]), "kb-m-p100": (w[2], w[2]), "kb-p-h001": (w[3], w[3])}
        for point in batch["points"]:
            name, description = names[point["id"]]
            entry = points.setdefault(point["id"], {})
            if batch["subject"] == "mathematics":
                entry["unit"] = "brueche-u2" if point["id"] == "kb-m-p101" else "brueche-u1"
            elif batch["subject"] == "physics":
                entry["unit"] = "physik-mechanik-u2"
            entry[locale] = {"name": name, "description": description,
                             "mastery": [f"{name} {i}" for i, _ in enumerate(point["mastery"])]}
        texts = {
            "kb-m-p101-q1": {"prompt": w[4], "answer": "3/4", "accepted": []},
            "kb-m-p101-q2": {"prompt": w[5], "choices": ["5/16", "5/8", w[9]]},
            "kb-m-p101-q3": {"prompt": w[6], "answer": "1/2, 1/2", "accepted": []},
            "kb-m-p100-q1": {"prompt": w[7], "answer": "1/4", "accepted": []},
            "kb-p-h001-q1": {"prompt": w[8], "answer": "5", "accepted": ["5 N"]},
        }
        for exercise in batch["exercises"]:
            exercises.setdefault(exercise["id"], {})[locale] = {
                **texts[exercise["id"]], "explanation": f"{locale}: {texts[exercise['id']]['prompt']}"
            }
    return {"batch": batch["batch"], "points": points, "exercises": exercises}


def _translated(tmp_path: Path) -> dict[str, Any]:
    source = kb.extract(_upstream(tmp_path))
    return kb.merge(source, [_translate(batch) for batch in kb.batches(source)])


# ── extract ──────────────────────────────────────────────────────────────────


def test_extract_leaves_every_textbook_record_behind(tmp_path: Path) -> None:
    source = kb.extract(_upstream(tmp_path))
    records = [*source["points"], *source["exercises"], *source["prerequisites"]]
    text = json.dumps(records, ensure_ascii=False)

    for field in ("chapter", "semester", "standards", "root_reason", "mathLinks"):
        assert f'"{field}"' not in text
    assert "cms-2022" not in text and "五年级下册" not in text
    assert source["leftBehind"]["fields"] == list(kb.TEXTBOOK_FIELDS)
    assert [p["id"] for p in source["points"]] == ["kb-m-p101", "kb-m-p100", "kb-p-h001"]
    assert all(not e["id"].startswith("cn") for e in source["exercises"])


def test_extract_skips_figures_and_self_assessments_and_keeps_the_rest(tmp_path: Path) -> None:
    source = kb.extract(_upstream(tmp_path))

    reasons = {row["sourceId"]: row["reason"] for row in source["skipped"]}
    assert set(reasons) == {"cnm_p101_q4", "cnm_p101_q5"}
    assert "figure" in reasons["cnm_p101_q4"]
    choice = next(e for e in source["exercises"] if e["id"] == "kb-m-p101-q2")
    assert choice["choices"] == ["5/16", "5/8", "1/8"] and choice["answerIndex"] == 1
    unordered = next(e for e in source["exercises"] if e["id"] == "kb-m-p101-q3")
    assert unordered["answer"] == "1/2, 1/2"
    physics = next(e for e in source["exercises"] if e["id"] == "kb-p-h001-q1")
    assert physics["mentionsTextbook"] is True


def test_extract_keeps_prerequisites_within_one_subject_only(tmp_path: Path) -> None:
    source = kb.extract(_upstream(tmp_path))

    assert source["prerequisites"] == [
        {"point": "kb-m-p101", "requires": "kb-m-p100", "strength": "hard"}
    ]


# ── merge ────────────────────────────────────────────────────────────────────


def test_a_clean_translation_merges_without_problems(tmp_path: Path) -> None:
    translated = _translated(tmp_path)

    assert translated["problems"] == []
    assert {p["id"]: p["unit"] for p in translated["points"]} == {
        "kb-m-p101": "brueche-u2", "kb-m-p100": "brueche-u1", "kb-p-h001": "physik-mechanik-u2",
    }
    assert len(translated["exercises"]) == 5


@pytest.mark.parametrize(
    ("exercise_id", "locale", "change", "problem"),
    [
        ("kb-m-p101-q1", "fr", {"prompt": "Calcule 1/4 + 2/4 ？"}, "Chinese left"),
        ("kb-m-p101-q1", "de", {"answer": "4/3"}, "is not the value"),
        ("kb-p-h001-q1", "it", {"explanation": "Come da 教材"}, "Chinese left"),
        ("kb-p-h001-q1", "en", {"explanation": "As the textbook says 本章"}, "textbook"),
        ("kb-m-p101-q2", "it", {"choices": ["5/16", "5/8"]}, "3 options expected"),
        ("kb-m-p101-q2", "de", {"choices": ["5/8", "5/8", "x"]}, "read the same"),
    ],
)
def test_merge_refuses_a_translation_that_breaks_a_rule(
    tmp_path: Path, exercise_id: str, locale: str, change: dict[str, Any], problem: str
) -> None:
    source = kb.extract(_upstream(tmp_path))
    filled = [_translate(batch) for batch in kb.batches(source)]
    for batch in filled:
        if exercise_id in batch["exercises"]:
            batch["exercises"][exercise_id][locale].update(change)

    merged = kb.merge(source, filled)

    found = next(row for row in merged["problems"] if row["id"] == exercise_id)
    assert any(problem in message for message in found["problems"])
    assert exercise_id not in {e["id"] for e in merged["exercises"]}


def test_merge_refuses_a_star_that_was_not_offered(tmp_path: Path) -> None:
    source = kb.extract(_upstream(tmp_path))
    filled = [_translate(batch) for batch in kb.batches(source)]
    filled[0]["points"]["kb-m-p101"]["unit"] = "physik-mechanik-u1"

    merged = kb.merge(source, filled)

    assert merged["problems"][0]["id"] == "kb-m-p101"
    assert "kb-m-p101" not in {p["id"] for p in merged["points"]}


def test_a_dropped_exercise_is_reported_with_the_translators_reason(tmp_path: Path) -> None:
    source = kb.extract(_upstream(tmp_path))
    filled = [_translate(batch) for batch in kb.batches(source)]
    filled[0]["exercises"]["kb-m-p101-q3"] = {"drop": "depends on Chinese characters"}

    merged = kb.merge(source, filled)

    assert merged["problems"] == []
    assert {"sourceId": "cnm_p101_q3", "reason": "translator: depends on Chinese characters"} in merged[
        "skipped"
    ]


# ── manifest ─────────────────────────────────────────────────────────────────


def test_every_lesson_is_a_draft_with_four_languages(tmp_path: Path) -> None:
    made, report = kb.manifests(_translated(tmp_path), "abc123")

    rows = [row for manifest in made for row in manifest["lessons"]]
    assert all(row["publish"] is False for row in rows)
    assert all("CC BY-NC" in manifest["operatorNote"] for manifest in made)
    lesson = next(row for row in rows if row["publicLessonId"] == "kb-m-p101")
    assert lesson["lesson"]["unitId"] == "brueche-u2" and lesson["lesson"]["topicId"] == "brueche"
    assert lesson["lesson"]["gradeLevel"] == "grade_5_primary"
    assert lesson["lesson"]["order"] == kb.FIRST_IMPORTED_ORDER
    choice = next(e for e in lesson["exercises"] if e["exerciseId"] == "kb-m-p101-q2")
    assert choice["type"] == "multiple_choice"
    assert choice["answerKey"] == "5/8" and choice["options"] == ["5/16", "5/8", "Mehr als 1"]
    assert choice["translations"]["fr"]["options"][2] == "Plus que 1"
    assert set(choice["translations"]) == {"en", "fr", "it"}
    unordered = next(e for e in lesson["exercises"] if e["exerciseId"] == "kb-m-p101-q3")
    assert unordered["type"] == "text_input" and unordered["skills"] == ["kb-m-p101"]
    physics = next(row for row in rows if row["publicLessonId"] == "kb-p-h001")
    assert physics["lesson"]["gradeLevel"] == "grade_secondary_ii"
    assert physics["lesson"]["topicId"] == "physik-mechanik"
    assert report["prerequisitesForLater"] == [
        {"point": "kb-m-p101", "requires": "kb-m-p100", "strength": "hard"}
    ]
    assert "五" not in json.dumps(made, ensure_ascii=False)


def test_an_exercise_over_the_authoring_limit_is_skipped_not_shortened(tmp_path: Path) -> None:
    translated = _translated(tmp_path)
    long = next(e for e in translated["exercises"] if e["id"] == "kb-m-p101-q1")
    long["text"]["it"]["prompt"] = "x" * (kb.MAX_TEXT + 1)

    made, report = kb.manifests(translated, "abc123")

    ids = {e["exerciseId"] for m in made for row in m["lessons"] for e in row["exercises"]}
    assert "kb-m-p101-q1" not in ids
    assert any(row["sourceId"] == "cnm_p101_q1" and "longer" in row["reason"] for row in report["skipped"])


def test_the_vocabulary_names_each_skill_in_four_languages(tmp_path: Path) -> None:
    vocabulary = kb.skill_vocabulary(_translated(tmp_path))

    assert vocabulary["skills"]["kb-m-p101"] == {
        "subject": "mathematics",
        "unit": "brueche-u2",
        "titles": {"de": "Brüche addieren", "en": "Adding fractions",
                   "fr": "Additionner des fractions", "it": "Addizionare frazioni"},
    }


# ── through the curriculum workflow ──────────────────────────────────────────


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    """The seed, with the knowledge base stars written the way --knowledge-base writes them."""
    table = install_seeded_table(monkeypatch)
    _subjects, topics, units = seed_practice.knowledge_base_rows(live=False)
    table.seed(
        *({"PK": "PRACTICE", "SK": f"TOPIC#{t['topic_id']}", **t} for t in topics),
        *({"PK": "PRACTICE", "SK": f"UNIT#{u['unit_id']}", **u} for u in units),
    )
    return table


def _register(monkeypatch: pytest.MonkeyPatch, vocabulary: dict[str, Any]) -> None:
    """Load a vocabulary the way curriculum_translations loads the committed one."""
    units = copy.deepcopy(curriculum_translations.SKILL_UNITS)
    titles = dict(curriculum_translations.SKILL_TITLES)
    translations = dict(curriculum_translations.TITLE_TRANSLATIONS)
    for skill_id, skill in vocabulary["skills"].items():
        units.setdefault(skill["subject"], {})[skill_id] = skill["unit"]
        titles[skill_id] = skill["titles"]["de"]
        translations[skill_id] = {locale: skill["titles"][locale] for locale in ("en", "fr", "it")}
    monkeypatch.setattr(curriculum_translations, "SKILL_UNITS", units)
    monkeypatch.setattr(curriculum_translations, "SKILL_TITLES", titles)
    monkeypatch.setattr(curriculum_translations, "TITLE_TRANSLATIONS", translations)


def _publish_all(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    translated = _translated(tmp_path)
    _register(monkeypatch, kb.skill_vocabulary(translated))
    made, _report = kb.manifests(translated, "abc123")
    for manifest in made:
        preview = curriculum_migration_service.dry_run(manifest, OPERATOR)
        assert preview["summary"]["errors"] == 0, [r["validationIssues"] for r in preview["rows"]]
        assert preview["publishReady"]
        applied = curriculum_migration_service.apply_migration(
            preview["migrationId"], manifest, preview["confirmationToken"], OPERATOR
        )
        for row in applied["rows"]:
            assert row["pointer"] is None
            public_id, version_id = row["publicLessonId"], row["versionId"]
            curriculum_ops_service.submit_review(public_id, version_id, OPERATOR)
            curriculum_ops_service.approve(public_id, version_id, OPERATOR)
            curriculum_ops_service.publish(
                public_id, version_id, OPERATOR, expected_published_version_id=None
            )


def test_the_manifests_dry_run_clean_and_apply_as_drafts_only(
    table: FakeTable, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    translated = _translated(tmp_path)
    _register(monkeypatch, kb.skill_vocabulary(translated))
    made, _report = kb.manifests(translated, "abc123")

    for manifest in made:
        preview = curriculum_migration_service.dry_run(manifest, OPERATOR)
        assert preview["summary"]["errors"] == 0
        curriculum_migration_service.apply_migration(
            preview["migrationId"], manifest, preview["confirmationToken"], OPERATOR
        )

    assert practice_repo.get_challenge("kb-m-p101-q2") is None


def test_a_published_exercise_reads_and_judges_in_the_students_language(
    table: FakeTable, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _publish_all(monkeypatch, tmp_path)
    row = practice_repo.get_challenge("kb-m-p101-q2")
    assert row is not None

    french = practice_projection_service.build_challenge_preview(row, "fr")
    assert french["prompt"].startswith("Noah mange")
    assert french["options"] == ["5/16", "5/8", "Plus que 1"]
    german = practice_projection_service.build_challenge_preview(row, "de")
    assert german["options"] == ["5/16", "5/8", "Mehr als 1"]

    shown = exercise_localization.localized(row, "fr")
    assert answer_judging.judge_challenge("5/8", shown)
    assert not answer_judging.judge_challenge("Plus que 1", shown)
    physics = exercise_localization.localized(practice_repo.get_challenge("kb-p-h001-q1"), "it")
    assert answer_judging.judge_challenge("5 N", physics)
    assert curriculum_translations.translated_title("kb-m-p101", "Brüche addieren", "it") == (
        "Addizionare frazioni"
    )


def test_a_translated_option_counts_in_its_language_and_in_german() -> None:
    challenge = {
        "type": "multiple_choice",
        "prompt": "Welche Zahl ist grösser?",
        "options": ["drei", "vier"],
        "correct_answer": "vier",
        "translations": {"fr": {"prompt": "Quel nombre est plus grand ?", "options": ["trois", "quatre"],
                                "correct_answer": "quatre"}},
    }

    shown = exercise_localization.localized(challenge, "fr")

    assert shown["options"] == ["trois", "quatre"]
    assert answer_judging.judge_challenge("quatre", shown)
    assert answer_judging.judge_challenge("vier", shown)
    assert not answer_judging.judge_challenge("trois", shown)
    assert exercise_localization.localized(challenge, "it")["options"] == ["drei", "vier"]
    assert challenge["options"] == ["drei", "vier"]


@pytest.mark.parametrize(
    ("exercise", "field"),
    [
        ({"type": "multiple_choice", "options": ["1"], "answer_key": "1"}, "options"),
        ({"type": "multiple_choice", "options": ["1", "2"], "answer_key": "3"}, "answer_key"),
        ({"type": "text_input", "options": ["1", "2"], "answer_key": "1"}, "options"),
        ({"type": "multiple_choice", "options": ["1", "2"], "answer_key": "2",
          "translations": {"fr": {"prompt": "?", "options": ["un", "deux"], "correct_answer": "un"}}},
         "translations.fr"),
        ({"type": "text_input", "answer_key": "2",
          "translations": {"es": {"prompt": "?", "correct_answer": "2"}}}, "translations.es"),
        ({"type": "text_input", "answer_key": "2", "translations": {"fr": {"prompt": "?"}}},
         "translations.fr"),
    ],
)
def test_authoring_refuses_options_and_translations_that_cannot_be_answered(
    exercise: dict[str, Any], field: str
) -> None:
    issues = curriculum_ops_service._choice_issues(exercise) + exercise_localization.translation_issues(  # noqa: SLF001
        exercise, max_text=curriculum_ops_service.MAX_EXERCISE_TEXT
    )

    assert field in [found for found, _message in issues]


def test_the_knowledge_base_stars_stay_hidden_until_they_go_live() -> None:
    subjects, topics, units = seed_practice.knowledge_base_rows(live=False)

    assert subjects == []
    assert {row["rollout_state"] for row in (*topics, *units)} == {"preview"}
    subjects, topics, units = seed_practice.knowledge_base_rows(live=True)
    assert [s["subject_id"] for s in subjects] == ["english", "physics"]
    assert {row["rollout_state"] for row in (*topics, *units)} == {"active"}


def test_the_catalog_files_each_new_star_under_an_existing_or_new_nebula() -> None:
    topics = {row["topic_id"] for row in knowledge_base_catalog.topics()}
    zap_topics = {unit.rsplit("-u", 1)[0] for unit in knowledge_base_catalog.ZAP_UNITS}
    units = knowledge_base_catalog.units()

    assert len({unit["unit_id"] for unit in units}) == len(units)
    assert not {unit["unit_id"] for unit in units} & set(knowledge_base_catalog.ZAP_UNITS)
    for unit in units:
        assert unit["topic_id"] in topics | zap_topics
        assert set(unit["titles"]) == set(knowledge_base_catalog.LOCALES)
    translations = knowledge_base_catalog.title_translations()
    assert translations["geometrie-u8"] == {"en": "Vectors", "fr": "Vecteurs", "it": "Vettori"}
    assert translations["physics"]["fr"] == "Physique"
