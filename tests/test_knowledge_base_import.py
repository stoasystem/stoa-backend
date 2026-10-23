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
    knowledge_map_service,
    knowledge_mastery_service,
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


# ── structure ────────────────────────────────────────────────────────────────

#: What the fake structurer tags each exercise as.
TYPES = {
    "kb-m-p101-q1": "kopfrechnen", "kb-m-p101-q2": "sachaufgaben", "kb-m-p101-q3": "schliessen",
    "kb-m-p100-q1": "darstellen", "kb-p-h001-q1": "rechnen",
}
STAR_NAMES = {
    "brueche-u2": ("brueche-addieren", ("Brüche addieren", "Adding fractions", "Additionner des fractions",
                                        "Addizionare frazioni")),
    "brueche-u1": ("bruchbegriff", ("Was ein Bruch ist", "What a fraction is", "Ce qu'est une fraction",
                                    "Che cos'è una frazione")),
    "physik-mechanik-u2": ("kraefte-addieren", ("Kräfte addieren", "Adding forces", "Additionner des forces",
                                                "Sommare forze")),
}


def _structure_out(batch: dict[str, Any]) -> dict[str, Any]:
    """Fill a structuring batch the way docs/knowledge-base-structure.md asks."""
    stars = []
    for group in batch["groups"]:
        slug, (de, en, fr, it) = STAR_NAMES[group["group"]]
        stars.append({
            "group": group["group"], "slug": slug,
            "titles": {"de": de, "en": en, "fr": fr, "it": it},
            "description": f"{de} im Alltag.",
            "points": [point["id"] for point in group["points"]],
        })
    exercises = {e["id"]: TYPES[e["id"]] for group in batch["groups"] for e in group["exercises"]}
    return {"batch": batch["batch"], "stars": stars, "exercises": exercises}


def _built(translated: dict[str, Any]) -> dict[str, Any]:
    return kb.structure(translated, [_structure_out(b) for b in kb.structure_batches(translated)])


def test_structure_makes_a_star_per_knowledge_point_beside_the_zap_stars(tmp_path: Path) -> None:
    built = _built(_translated(tmp_path))

    assert built["problems"] == []
    assert set(built["stars"]) == {
        "brueche-brueche-addieren", "brueche-bruchbegriff", "physik-mechanik-kraefte-addieren",
    }
    star = built["stars"]["brueche-bruchbegriff"]
    assert star["topic_id"] == "brueche" and star["subject_id"] == "mathematics"
    # After the two seeded ZAP stars of the fractions nebula, by the youngest grade.
    assert star["order"] == 3
    assert built["points"]["kb-m-p101"] == "brueche-brueche-addieren"
    assert built["exercises"]["kb-m-p101-q2"] == "sachaufgaben"
    # The upstream edge p101 -> p100 becomes an edge between their stars.
    assert built["stars"]["brueche-brueche-addieren"]["prerequisites"] == ["brueche-bruchbegriff"]


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda out: out["stars"][0]["points"].append("kb-m-p100"), "not in exactly one star"),
        (lambda out: out["stars"][0].update(slug="Brüche addieren"), "slug"),
        (lambda out: out["stars"][0]["titles"].update(fr="分数"), "Chinese"),
        (lambda out: out["stars"][0].update(points=[f"p{i}" for i in range(13)]), "not in exactly one star"),
        (lambda out: out["exercises"].update({"kb-m-p101-q1": "raten"}), "question type"),
    ],
)
def test_structure_refuses_what_breaks_a_rule(tmp_path: Path, change: Any, problem: str) -> None:
    translated = _translated(tmp_path)
    filled = [_structure_out(b) for b in kb.structure_batches(translated)]
    change(filled[0])

    built = kb.structure(translated, filled)

    assert any(problem in message for row in built["problems"] for message in row["problems"])


def test_a_star_of_too_many_points_is_refused() -> None:
    star = {"slug": "gross", "titles": {locale: "Gross" for locale in kb.LOCALES}, "description": "Viel.",
            "points": [f"p{i}" for i in range(knowledge_base_catalog.MAX_POINTS_PER_STAR + 1)]}

    assert any("more than" in problem for problem in kb._star_problems(star))  # noqa: SLF001


def test_star_prerequisites_keep_the_heaviest_links_and_never_a_cycle() -> None:
    point_star = {"a1": "A", "a2": "A", "b1": "B", "c1": "C"}
    edges = [
        {"point": "a1", "requires": "b1", "strength": "hard"},
        {"point": "a2", "requires": "b1", "strength": "hard"},
        {"point": "b1", "requires": "a1", "strength": "hard"},
        {"point": "b1", "requires": "c1", "strength": "hard"},
        {"point": "c1", "requires": "a1", "strength": "soft"},
    ]

    assert kb.star_prerequisites(point_star, edges) == {"A": ["B"], "B": ["C"]}


def _merge(nebula: str, slug: str, sources: list[str]) -> dict[str, Any]:
    return {"nebula": nebula, "stars": [{
        "slug": slug, "titles": {locale: slug for locale in kb.LOCALES},
        "description": "Zusammengeführt.", "from": sources,
    }]}


def test_the_merge_pass_joins_stars_of_a_nebula_whole(tmp_path: Path) -> None:
    translated = _translated(tmp_path)
    filled = [_structure_out(b) for b in kb.structure_batches(translated)]
    merge = _merge("brueche", "brueche-verstehen-und-addieren",
                   ["brueche-brueche-addieren", "brueche-bruchbegriff"])

    built = kb.structure(translated, filled, [merge])

    assert built["problems"] == []
    assert "brueche-brueche-verstehen-und-addieren" in built["stars"]
    assert "brueche-bruchbegriff" not in built["stars"]
    # The nebula without a merge keeps its stars.
    assert "physik-mechanik-kraefte-addieren" in built["stars"]
    star = built["stars"]["brueche-brueche-verstehen-und-addieren"]
    assert star["points"] == ["kb-m-p100", "kb-m-p101"]
    assert built["points"]["kb-m-p100"] == "brueche-brueche-verstehen-und-addieren"


@pytest.mark.parametrize(
    ("sources", "problem"),
    [
        (["brueche-brueche-addieren"], "not in exactly one merged star"),
        (["brueche-brueche-addieren", "brueche-bruchbegriff", "brueche-anderes"], "not in exactly one"),
    ],
)
def test_the_merge_pass_refuses_a_star_left_out_or_unknown(
    tmp_path: Path, sources: list[str], problem: str
) -> None:
    translated = _translated(tmp_path)
    filled = [_structure_out(b) for b in kb.structure_batches(translated)]

    built = kb.structure(translated, filled, [_merge("brueche", "alles", sources)])

    assert any(problem in message for row in built["problems"] for message in row["problems"])


def test_the_merge_pass_refuses_a_star_too_small_or_too_large() -> None:
    points = {f"p{i}": {"grade": 1, "sourceId": f"cnm_{i}"} for i in range(14)}
    stars = {
        f"zahlen-s{i}": {"topic_id": "zahlen", "subject_id": "mathematics", "points": [f"p{i}"],
                         "titles": {}, "description": "", "grades": [1, 1]}
        for i in range(14)
    }
    split = {"nebula": "zahlen", "stars": [
        {"slug": "klein", "titles": {locale: "Klein" for locale in kb.LOCALES}, "description": "Klein.",
         "from": ["zahlen-s0"]},
        {"slug": "gross", "titles": {locale: "Gross" for locale in kb.LOCALES}, "description": "Gross.",
         "from": [f"zahlen-s{i}" for i in range(1, 14)]},
    ]}

    _merged, _point_star, problems = kb.apply_merges(stars, [split], points)

    messages = [message for row in problems for message in row["problems"]]
    assert any("fewer than" in message for message in messages)
    assert any("more than" in message for message in messages)


# ── manifest ─────────────────────────────────────────────────────────────────


def _manifests(tmp_path: Path):
    translated = _translated(tmp_path)
    return kb.manifests(translated, _built(translated), "abc123")


def test_every_practice_set_is_a_draft_of_one_small_star_in_four_languages(tmp_path: Path) -> None:
    made, report, stars_file, vocabulary = _manifests(tmp_path)

    rows = {row["publicLessonId"]: row for manifest in made for row in manifest["lessons"]}
    assert all(row["publish"] is False for row in rows.values())
    assert all("CC BY-NC" in manifest["operatorNote"] for manifest in made)
    word_problems = rows["brueche-brueche-addieren--sachaufgaben--1"]
    assert word_problems["lesson"]["unitId"] == "brueche-brueche-addieren"
    assert word_problems["lesson"]["topicId"] == "brueche"
    assert word_problems["lesson"]["title"] == "Sachaufgaben"
    assert word_problems["lesson"]["gradeLevel"] == "grade_5_primary"
    assert word_problems["lesson"]["extension"] is False
    # p101 needs p100, which sits in another star: the set says so, it is not locked.
    assert word_problems["lesson"]["requiresPoints"] == ["kb-m-p100"]
    [choice] = word_problems["exercises"]
    assert choice["type"] == "multiple_choice" and choice["skills"] == ["brueche-brueche-addieren--sachaufgaben"]
    assert choice["knowledgePoint"] == "kb-m-p101"
    assert choice["answerKey"] == "5/8" and choice["options"] == ["5/16", "5/8", "Mehr als 1"]
    assert choice["translations"]["fr"]["options"][2] == "Plus que 1"
    assert set(choice["translations"]) == {"en", "fr", "it"}
    assert set(rows) == {
        "brueche-brueche-addieren--kopfrechnen--1", "brueche-brueche-addieren--sachaufgaben--1",
        "brueche-brueche-addieren--schliessen--1", "brueche-bruchbegriff--darstellen--1",
        "physik-mechanik-kraefte-addieren--rechnen--1",
    }
    assert rows["brueche-brueche-addieren--schliessen--1"]["lesson"]["extension"] is True
    physics = rows["physik-mechanik-kraefte-addieren--rechnen--1"]
    assert physics["lesson"]["gradeLevel"] == "grade_secondary_ii"
    assert stars_file["stars"]["brueche-brueche-addieren"]["prerequisites"] == ["brueche-bruchbegriff"]
    assert vocabulary["skills"]["brueche-brueche-addieren--kopfrechnen"] == {
        "subject": "mathematics",
        "unit": "brueche-brueche-addieren",
        "titles": {"de": "Kopfrechnen-Trick", "en": "Mental maths tricks",
                   "fr": "Astuces de calcul mental", "it": "Trucchi di calcolo mentale"},
        "extension": False,
    }
    assert vocabulary["skills"]["brueche-brueche-addieren--schliessen"]["extension"] is True
    assert report["summary"]["smallStars"] == 5
    assert "五" not in json.dumps(made, ensure_ascii=False)


def test_a_large_small_star_is_cut_into_numbered_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kb, "EXERCISES_PER_SET", 1)
    translated = _translated(tmp_path)
    built = _built(translated)
    built["exercises"]["kb-m-p101-q3"] = "kopfrechnen"

    made, _report, _stars, vocabulary = kb.manifests(translated, built, "abc123")

    ids = [row["publicLessonId"] for m in made for row in m["lessons"]]
    assert "brueche-brueche-addieren--kopfrechnen--1-1" in ids
    assert "brueche-brueche-addieren--kopfrechnen--1-2" in ids
    assert vocabulary["practiceSets"]["brueche-brueche-addieren--kopfrechnen--1-2"]["fr"] == (
        "Astuces de calcul mental · Partie 2"
    )


def test_a_star_is_layered_by_what_its_knowledge_points_need() -> None:
    edges = [
        {"point": "b", "requires": "a", "strength": "hard"},
        {"point": "c", "requires": "b", "strength": "hard"},
        {"point": "d", "requires": "a", "strength": "soft"},
        {"point": "a", "requires": "c", "strength": "hard"},  # would close a cycle
        {"point": "b", "requires": "x", "strength": "hard"},  # in another star
    ]

    assert kb.point_layers(["a", "b", "c", "d"], edges) == {"a": 1, "b": 2, "c": 3, "d": 1}
    chain = [{"point": f"p{i + 1}", "requires": f"p{i}", "strength": "hard"} for i in range(6)]
    assert kb.point_layers([f"p{i}" for i in range(7)], chain)["p6"] == kb.MAX_LAYERS


def test_layers_become_stages_of_one_small_star_in_order(tmp_path: Path) -> None:
    translated = _translated(tmp_path)
    built = _built(translated)
    # Both points in one star: p101 needs p100, so it is the second layer.
    star = built["stars"]["brueche-brueche-addieren"]
    star["points"] = ["kb-m-p100", "kb-m-p101"]
    del built["stars"]["brueche-bruchbegriff"]
    built["points"]["kb-m-p100"] = "brueche-brueche-addieren"
    built["exercises"]["kb-m-p100-q1"] = "kopfrechnen"

    made, _report, _stars, vocabulary = kb.manifests(translated, built, "abc123")

    rows = {row["publicLessonId"]: row["lesson"] for m in made for row in m["lessons"]}
    first, second = rows["brueche-brueche-addieren--kopfrechnen--1"], rows["brueche-brueche-addieren--kopfrechnen--2"]
    assert first["order"] < second["order"]
    assert first["requiresPoints"] == [] and second["requiresPoints"] == ["kb-m-p100"]
    assert vocabulary["practiceSets"]["brueche-brueche-addieren--kopfrechnen--2"]["en"] == (
        "Mental maths tricks · Level 2"
    )


def test_an_exercise_over_the_authoring_limit_is_skipped_not_shortened(tmp_path: Path) -> None:
    translated = _translated(tmp_path)
    long = next(e for e in translated["exercises"] if e["id"] == "kb-m-p101-q1")
    long["text"]["it"]["prompt"] = "x" * (kb.MAX_TEXT + 1)

    made, report, _stars, _vocabulary = kb.manifests(translated, _built(translated), "abc123")

    ids = {e["exerciseId"] for m in made for row in m["lessons"] for e in row["exercises"]}
    assert "kb-m-p101-q1" not in ids
    assert any(row["sourceId"] == "cnm_p101_q1" and "longer" in row["reason"] for row in report["skipped"])


# ── through the curriculum workflow ──────────────────────────────────────────


def _register(
    monkeypatch: pytest.MonkeyPatch, stars_file: dict[str, Any], vocabulary: dict[str, Any]
) -> None:
    """Load the generated files the way the catalog and curriculum_translations load the committed ones."""
    monkeypatch.setattr(knowledge_base_catalog, "_stars_data", lambda: stars_file)
    monkeypatch.setattr(knowledge_base_catalog, "_skills_data", lambda: vocabulary)
    units = copy.deepcopy(curriculum_translations.SKILL_UNITS)
    titles = dict(curriculum_translations.SKILL_TITLES)
    translations = dict(curriculum_translations.TITLE_TRANSLATIONS)
    translations.update(knowledge_base_catalog.title_translations())
    for skill_id, skill in vocabulary["skills"].items():
        units.setdefault(skill["subject"], {})[skill_id] = skill["unit"]
        titles[skill_id] = skill["titles"]["de"]
        translations[skill_id] = {locale: skill["titles"][locale] for locale in ("en", "fr", "it")}
    monkeypatch.setattr(curriculum_translations, "SKILL_UNITS", units)
    monkeypatch.setattr(curriculum_translations, "SKILL_TITLES", titles)
    monkeypatch.setattr(curriculum_translations, "TITLE_TRANSLATIONS", translations)


@pytest.fixture
def imported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[dict[str, Any]]:
    """The seed with the knowledge base stars written the way --knowledge-base writes them;
    returns the manifests."""
    made, _report, stars_file, vocabulary = _manifests(tmp_path)
    _register(monkeypatch, stars_file, vocabulary)
    table = install_seeded_table(monkeypatch)
    _subjects, topics, units = seed_practice.knowledge_base_rows(live=False)
    table.seed(
        *({"PK": "PRACTICE", "SK": f"TOPIC#{t['topic_id']}", **t} for t in topics),
        *({"PK": "PRACTICE", "SK": f"UNIT#{u['unit_id']}", **u} for u in units),
    )
    return made


def _publish_all(made: list[dict[str, Any]]) -> None:
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


def test_the_manifests_dry_run_clean_and_apply_as_drafts_only(imported: list[dict[str, Any]]) -> None:
    for manifest in imported:
        preview = curriculum_migration_service.dry_run(manifest, OPERATOR)
        assert preview["summary"]["errors"] == 0
        curriculum_migration_service.apply_migration(
            preview["migrationId"], manifest, preview["confirmationToken"], OPERATOR
        )

    assert practice_repo.get_challenge("kb-m-p101-q2") is None


def test_a_published_exercise_reads_and_judges_in_the_students_language(
    imported: list[dict[str, Any]],
) -> None:
    _publish_all(imported)
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
    assert curriculum_translations.translated_title(
        "brueche-brueche-addieren--sachaufgaben--1", "Sachaufgaben", "it"
    ) == "Problemi"
    assert curriculum_translations.translated_title(
        "brueche-brueche-addieren", "Brüche addieren", "fr"
    ) == "Additionner des fractions"


def test_a_student_is_told_what_to_master_first_and_nothing_is_locked(
    imported: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _publish_all(imported)
    # Live, as --knowledge-base-live writes them once the sets are published.
    _subjects, topics, units = seed_practice.knowledge_base_rows(live=True)
    practice_repo.get_table().seed(
        *({"PK": "PRACTICE", "SK": f"TOPIC#{t['topic_id']}", **t} for t in topics),
        *({"PK": "PRACTICE", "SK": f"UNIT#{u['unit_id']}", **u} for u in units),
    )
    answered: set[str] = set()
    monkeypatch.setattr(
        knowledge_mastery_service.practice_repo, "all_challenges_answered_right", lambda _s: set(answered)
    )

    def skill(skill_id: str) -> knowledge_mastery_service.SkillMastery:
        return knowledge_mastery_service.skill_states("student-1", subject_id="mathematics")[skill_id]

    before = skill("brueche-brueche-addieren--sachaufgaben")
    assert before.ready is False and before.missing_unit_ids == ("brueche-bruchbegriff",)
    assert skill("brueche-brueche-addieren--schliessen").extension is True

    answered.add("kb-m-p100-q1")
    assert skill("brueche-brueche-addieren--sachaufgaben").ready is True


def test_a_star_lights_from_its_core_and_extension_practice_is_beside_it() -> None:
    lessons = [{"id": "core"}, {"id": "proof", "extension": True}]
    exercises = {"core": ["c1"], "proof": ["p1"]}

    judged = knowledge_mastery_service.judge_unit(
        unit={"id": "u"}, lessons=lessons, exercises_by_lesson=exercises,
        completed_lesson_ids=frozenset({"core"}), exercises_answered_right=frozenset({"c1"}),
    )

    assert judged.state is knowledge_mastery_service.LearningState.LIT
    assert judged.lesson_count == 1
    assert judged.next_lesson is not None and judged.next_lesson.lesson_id == "proof"
    # A unit of nothing but extensions lights from all of them.
    only = knowledge_mastery_service.judge_unit(
        unit={"id": "u"}, lessons=[{"id": "proof", "extension": True}], exercises_by_lesson=exercises,
        completed_lesson_ids=frozenset(), exercises_answered_right=frozenset(),
    )
    assert only.lesson_count == 1 and only.state is knowledge_mastery_service.LearningState.READY


def test_the_star_map_names_missing_knowledge_and_extension_small_stars() -> None:
    states = {
        "u--a": knowledge_mastery_service.SkillMastery("u--a", "u", False, extension=True),
        "u--b": knowledge_mastery_service.SkillMastery(
            "u--b", "u", False, ready=False, missing_unit_ids=("v",)
        ),
    }

    skills = knowledge_map_service._skills_of("u", states, "de", {"v": "Brüche verstehen"})  # noqa: SLF001

    assert skills[0]["extension"] is True and "missingPrerequisites" not in skills[0]
    assert skills[1]["missingPrerequisites"] == [{"unitId": "v", "name": "Brüche verstehen"}]


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


def test_the_knowledge_base_stars_stay_hidden_until_they_go_live(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _made, _report, stars_file, vocabulary = _manifests(tmp_path)
    _register(monkeypatch, stars_file, vocabulary)

    subjects, topics, units = seed_practice.knowledge_base_rows(live=False)
    assert subjects == []
    assert {row["rollout_state"] for row in (*topics, *units)} == {"preview"}
    assert all(unit["prerequisite_unit_ids"] == [] for unit in units)
    subjects, topics, units = seed_practice.knowledge_base_rows(live=True, prerequisites=True)
    assert [s["subject_id"] for s in subjects] == ["english", "physics"]
    assert {row["rollout_state"] for row in (*topics, *units)} == {"active"}
    prerequisites = {unit["unit_id"]: unit["prerequisite_unit_ids"] for unit in units}
    assert prerequisites["brueche-brueche-addieren"] == ["brueche-bruchbegriff"]


def test_a_language_is_laid_out_by_situations_of_life_and_by_grammar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    english = knowledge_base_catalog.unit_choices("english")

    assert "englisch-schule-klassenzimmer" in english
    assert "englisch-verben-vergangenheit" in english
    assert all(unit.startswith("englisch-") for unit in english)
    nebulae = [t["topic_id"] for t in knowledge_base_catalog.topics() if t["subject_id"] == "english"]
    assert nebulae[0] == "englisch-ich" and nebulae[-1] == "englisch-saetze"

    # Another language gets the same nebulae under its own prefix.
    monkeypatch.setattr(
        knowledge_base_catalog, "LANGUAGE_SUBJECTS", {"english": "englisch", "german": "deutsch"}
    )
    german = knowledge_base_catalog.unit_choices("german")
    assert {unit.removeprefix("deutsch-") for unit in german} == {
        unit.removeprefix("englisch-") for unit in english
    }
    assert knowledge_base_catalog.subject_of_topic("deutsch-verben") == "german"


def test_the_coarse_stars_lie_in_an_existing_or_new_nebula() -> None:
    topics = {row["topic_id"] for row in knowledge_base_catalog.topics()}
    zap_topics = {unit.rsplit("-u", 1)[0] for unit in knowledge_base_catalog.ZAP_UNITS}
    units = knowledge_base_catalog.grouping_units()

    assert len({unit["unit_id"] for unit in units}) == len(units)
    assert not {unit["unit_id"] for unit in units} & set(knowledge_base_catalog.ZAP_UNITS)
    for unit in units:
        assert unit["topic_id"] in topics | zap_topics
        assert set(unit["titles"]) == set(knowledge_base_catalog.LOCALES)
    assert knowledge_base_catalog.topic_of_group("brueche-u2") == "brueche"
    assert knowledge_base_catalog.title_translations()["physics"]["fr"] == "Physique"


def test_every_subject_has_question_types_in_four_languages() -> None:
    for subject in ("mathematics", "english", "physics"):
        types = knowledge_base_catalog.QUESTION_TYPES[subject]
        assert len({slug for slug, _titles, _scope in types}) == len(types)
        for _slug, titles, scope in types:
            assert set(titles) == set(knowledge_base_catalog.LOCALES) and scope


def test_the_committed_stars_and_skills_agree() -> None:
    """Every small star in the committed vocabulary hangs under a committed star."""
    stars = {unit["unit_id"] for unit in knowledge_base_catalog.units()}
    skills = knowledge_base_catalog.skills()

    assert {skill["unit"] for skill in skills.values()} <= stars
    for unit in knowledge_base_catalog.units():
        assert set(unit["prerequisites"]) <= stars
