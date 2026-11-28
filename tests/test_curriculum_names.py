"""One module names curriculum content for a reader (#660).

`curriculum_names` names a topic, unit, lesson or skill point in the reader's
language (`name`) and recognises any spelling of one (`resolve`). These tests
say what the two answer, and keep the naming in that one module: nothing else
in `src/stoa` reads the name tables, and every read of a `title` elsewhere is
listed here with why it is not naming content. That the responses did not
change is `tests/test_curriculum_names_unchanged.py`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from stoa.services import curriculum_names, curriculum_translations

SRC = Path(__file__).resolve().parents[1] / "src" / "stoa"
MODULE = "services/curriculum_names.py"

CATALOG = {
    "topics": [
        {"id": "brueche", "subjectId": "math", "title": "Brüche"},
        {"id": "two-units", "subjectId": "math", "title": "Zwei Sterne"},
    ],
    "units": [
        {"id": "brueche-u1", "subjectId": "math", "topicId": "brueche", "title": "Brüche verstehen"},
        {"id": "two-a", "subjectId": "math", "topicId": "two-units", "title": "Erster"},
        {"id": "two-b", "subjectId": "math", "topicId": "two-units", "title": "Zweiter"},
    ],
    "lessons": [
        {"id": "brueche-l1", "unitId": "brueche-u1", "title": "Brüche lesen"},
        {"id": "orphan-lesson", "unitId": "gone", "title": "Verwaist"},
    ],
}


# ── name ────────────────────────────────────────────────────────────────────


def test_a_stored_row_is_named_by_the_names_it_carries() -> None:
    titles = {"de": "Brüche lesen", "en": "Reading fractions", "fr": "Lire", "it": "Leggere"}
    row = {
        "lesson_id": "brueche-l1",
        "unit_id": "brueche-u1",
        "topic_id": "brueche",
        "title": "Brüche lesen",
        "titles": titles,
    }

    for locale, name in titles.items():
        assert curriculum_names.for_reader(locale, rows=[row]).name("brueche-l1") == name
    # A lesson row is named under its own id, not the unit or topic it carries.
    assert curriculum_names.for_reader("de", rows=[row]).name("brueche-u1") is None


def test_an_untranslated_row_keeps_its_german_title_in_every_language() -> None:
    row = {"unit_id": "new-unit", "topic_id": "brueche", "title": "Neuer Stern"}

    for locale in ("de", "en", "fr", "it"):
        assert curriculum_names.for_reader(locale, rows=[row]).name("new-unit") == "Neuer Stern"


def test_the_catalog_title_is_the_name_it_shows() -> None:
    names = curriculum_names.for_reader("de", catalog=CATALOG)

    assert names.name("brueche-u1") == "Brüche verstehen"
    assert names.name("two-units") == "Zwei Sterne"
    assert names.name("brueche-l1") == "Brüche lesen"


def test_a_skill_point_is_named_by_its_own_name_and_its_translation() -> None:
    assert curriculum_names.for_reader("de").name("brueche-kuerzen") == "Brüche kürzen"
    assert curriculum_names.for_reader("en").name("brueche-kuerzen") == (
        curriculum_translations.SKILL_TRANSLATIONS["brueche-kuerzen"]["en"]
    )


@pytest.mark.parametrize("unknown", ["no-such-content", "", None, 7])
def test_an_id_nobody_knows_has_no_name(unknown: object) -> None:
    for locale in ("de", "en"):
        assert curriculum_names.for_reader(locale, catalog=CATALOG).name(unknown) is None


def test_german_is_never_looked_up_in_the_translations() -> None:
    """The subject's stored id has English, French and Italian names and no German one."""
    assert curriculum_names.for_reader("de").name("mathematics") is None
    assert curriculum_names.for_reader("en").name("mathematics") == "Mathematics"


def test_a_blank_title_is_no_name() -> None:
    row = {"topic_id": "blank-topic", "title": "  "}

    assert curriculum_names.for_reader("de", rows=[row]).name("blank-topic") is None


# ── resolve ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "spelling",
    [
        "brueche-u1",  # the unit id
        "brueche-l1",  # a lesson of it
        "brueche",  # its topic, which has only this unit
        "Brüche verstehen",  # its German title
        "BRÜCHE VERSTEHEN ",  # spelled loosely
        "brueche-kuerzen",  # a skill point under it
        "Brüche kürzen",  # that skill point's name
    ],
)
def test_every_spelling_of_a_knowledge_point_resolves_to_its_unit(spelling: str) -> None:
    names = curriculum_names.for_reader("de", catalog=CATALOG)

    assert names.resolve(spelling) == "brueche-u1"


def test_a_translated_title_resolves_whatever_the_reader_reads() -> None:
    row = {
        "unit_id": "brueche-u1",
        "title": "Brüche verstehen",
        "titles": {"de": "Brüche verstehen", "en": "Understanding fractions"},
    }

    names = curriculum_names.for_reader("fr", catalog=CATALOG, rows=[row])
    assert names.resolve("Understanding fractions") == "brueche-u1"
    # The catalog alone shows one language; the rows tell the others.
    assert curriculum_names.for_reader("fr", catalog=CATALOG).resolve("Understanding fractions") is None


def test_a_topic_with_several_units_stays_the_topic() -> None:
    names = curriculum_names.for_reader("de", catalog=CATALOG)

    assert names.resolve("two-units") == "two-units"
    assert names.resolve("Zwei Sterne") == "two-units"


def test_what_the_curriculum_does_not_know_does_not_resolve() -> None:
    names = curriculum_names.for_reader("de", catalog=CATALOG)

    assert names.resolve("Freies Thema") is None
    assert names.resolve("orphan-lesson") is None
    assert names.resolve("", None, 3) is None
    assert curriculum_names.for_reader("de").resolve("brueche-u1") is None


def test_the_ids_a_row_recorded_count_before_its_spellings_when_the_catalog_has_them() -> None:
    names = curriculum_names.for_reader("de", catalog=CATALOG)

    assert names.resolve("two-units", unit_id="two-b") == "two-b"
    assert names.resolve("two-units", lesson_id="brueche-l1") == "brueche-u1"
    # An id the catalog does not have as a unit or a unit's lesson is passed over.
    assert names.resolve("two-units", unit_id="brueche", lesson_id="orphan-lesson") == "two-units"


# ── the gate: naming content happens here only ──────────────────────────────

#: The modules that define the name tables; they hold them, they do not read
#: them to name anything.
_TABLE_OWNERS = {"services/curriculum_translations.py", "services/knowledge_base_catalog.py"}
_TABLES = {"SUBJECT_TRANSLATIONS", "SKILL_TRANSLATIONS", "SKILL_TITLES"}
#: Gone: the old ways of naming content (#660), and the table that named topics,
#: units and lessons before their rows did (#661).
_RETIRED = {
    "translated_title",
    "skill_title",
    "TopicNames",
    "_every_title",
    "_subject_display_label",
    "TITLE_TRANSLATIONS",
    "title_translations",
}

#: Every read of a `title` or `titles` in src/stoa outside curriculum_names, by
#: module and function, and why it does not name a topic, unit, lesson or skill
#: point from a stored content row. A new one is either one of these or goes
#: through `curriculum_names`.
_CATALOG = "the student catalog's title, which curriculum_names gave it"
_NOT_CONTENT = "the title of something that is not a topic, unit, lesson or skill point"
_WRITER = "writes or checks a content row for an operator, not a reader"
_SOURCE = "the knowledge base's own names, which the seed and the import write onto rows"
TITLE_READS: dict[tuple[str, str], str] = {
    ("db/repositories/curriculum_ops_repo.py", "_kept_titles"): _WRITER,
    ("db/repositories/curriculum_ops_repo.py", "put_published_projection"): _WRITER,
    ("db/repositories/notification_repo.py", "_global_classification_facts"): _NOT_CONTENT,
    ("db/repositories/notification_repo.py", "validate_global_nonprivate_event"): _NOT_CONTENT,
    ("operator_calls/curriculum.py", "_title"): _WRITER,
    ("routers/conversations.py", "_adopt_question_as_title"): _NOT_CONTENT,
    ("routers/conversations.py", "_conversation_title"): _NOT_CONTENT,
    ("routers/parents.py", "_star_answers"): _CATALOG,
    ("routers/teachers.py", "_ai_helped_stars"): _CATALOG,
    ("routers/teachers.py", "_asked_stars"): _CATALOG,
    ("services/adaptive_learning_service.py", "_assignment_source"): _NOT_CONTENT,
    ("services/adaptive_learning_service.py", "_automation_execution_candidate"): _NOT_CONTENT,
    ("services/adaptive_learning_service.py", "_create_assignment_item"): _NOT_CONTENT,
    ("services/adaptive_learning_service.py", "_curriculum_exercise_candidates"): _NOT_CONTENT,
    (
        "services/adaptive_learning_service.py",
        "_execute_assignment_automation_candidate",
    ): _NOT_CONTENT,
    ("services/adaptive_learning_service.py", "_reviewed_draft_candidates"): _NOT_CONTENT,
    ("services/adaptive_learning_service.py", "assignment_response"): _NOT_CONTENT,
    ("services/curriculum_migration_service.py", "_normalize_row"): _WRITER,
    ("services/curriculum_ops_service.py", "_lesson_payload"): _WRITER,
    ("services/curriculum_ops_service.py", "_patch_lesson"): _WRITER,
    ("services/curriculum_ops_service.py", "lesson_missing_locales"): _WRITER,
    ("services/curriculum_ops_service.py", "named_lesson"): _WRITER,
    ("services/curriculum_translations.py", "<module>"): _SOURCE,
    ("services/knowledge_base_catalog.py", "unit_choices"): _SOURCE,
    ("services/knowledge_map_service.py", "_practice_sets"): _CATALOG,
    ("services/knowledge_map_service.py", "build_map"): _CATALOG,
    ("services/knowledge_mastery_service.py", "judge_unit"): _CATALOG,
    ("services/lesson_sections.py", "localized"): _NOT_CONTENT,
    ("services/notifications/_bell.py", "_event_text"): _NOT_CONTENT,
    ("services/notifications/_push.py", "attempt_push_delivery"): _NOT_CONTENT,
    ("services/notifications/_realtime.py", "event_envelope"): _NOT_CONTENT,
    ("services/practice_context_service.py", "resolve"): _CATALOG,
    ("services/report_service.py", "_stars_lit"): _CATALOG,
    ("services/report_service.py", "build_bedrock_report_input"): _NOT_CONTENT,
    ("services/star_map_candidates.py", "from_catalog"): _CATALOG,
}


def _modules() -> list[tuple[str, ast.Module]]:
    return [
        (path.relative_to(SRC).as_posix(), ast.parse(path.read_text(encoding="utf-8")))
        for path in sorted(SRC.rglob("*.py"))
    ]


def _identifiers(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.alias):
            found.add(node.asname or node.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.add(node.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
    return found


_NAME_KEYS = {"title", "titles"}


def _title_reads(tree: ast.Module) -> set[str]:
    """The functions that read a `title` or `titles` key: `x["title"]` or `x.get("title", ...)`."""
    found: set[str] = set()

    def visit(node: ast.AST, where: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = where
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                inner = child.name
            if (
                isinstance(child, ast.Subscript)
                and isinstance(child.ctx, ast.Load)
                and isinstance(child.slice, ast.Constant)
                and child.slice.value in _NAME_KEYS
            ) or (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr in {"get", "pop", "setdefault"}
                and child.args
                and isinstance(child.args[0], ast.Constant)
                and child.args[0].value in _NAME_KEYS
            ):
                found.add(where)
            visit(child, inner)

    visit(tree, "<module>")
    return found


def test_only_curriculum_names_reads_the_name_tables() -> None:
    readers = {
        module: sorted(_identifiers(tree) & _TABLES)
        for module, tree in _modules()
        if module != MODULE and module not in _TABLE_OWNERS
    }

    assert {module: found for module, found in readers.items() if found} == {}


def test_the_old_ways_of_naming_content_are_gone() -> None:
    left = {module: sorted(_identifiers(tree) & _RETIRED) for module, tree in _modules()}

    assert {module: found for module, found in left.items() if found} == {}


def test_every_title_read_outside_curriculum_names_is_listed() -> None:
    reads = {
        (module, function)
        for module, tree in _modules()
        if module != MODULE
        for function in _title_reads(tree)
    }

    assert sorted(reads - set(TITLE_READS)) == [], "name content through curriculum_names"
    assert sorted(set(TITLE_READS) - reads) == [], "a listed read is gone: drop it from TITLE_READS"
