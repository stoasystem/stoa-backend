"""Content rows carry their names in every language (#661).

A topic, unit or lesson row holds `titles` - German, English, French, Italian -
with the German one also its `title`. The writers give it: the seed, the
knowledge-base import (`test_knowledge_base_import.py`), and the curriculum
authoring and migrations, whose publish puts a lesson's names on its row.
`curriculum_names` names content by them before the translation table, which
holds the names of the rows written before them until the backfill
(`test_backfill_content_titles.py`).
"""

from __future__ import annotations

from typing import Any

import pytest

import test_curriculum_publish_projection as published
from fakes.dynamodb import FakeTable
from scripts import seed_practice
from stoa.services import (
    curriculum_migration_service,
    curriculum_names,
    curriculum_ops_service,
    curriculum_service,
    curriculum_translations,
    knowledge_base_catalog,
)

LESSON_ID = published.LESSON_ID
TITLES = {
    "de": "Brüche addieren",
    "en": "Adding fractions",
    "fr": "Additionner des fractions",
    "it": "Sommare frazioni",
}


# ── what a reader is shown ──────────────────────────────────────────────────


def test_normalized_titles_keeps_each_languages_name_and_german_is_the_title() -> None:
    assert curriculum_names.normalized_titles(
        {"it": " Frazioni ", "en": "Fractions", "fr": "", "xx": "Brøk", "de": 3}, german=" Brüche "
    ) == {"de": "Brüche", "en": "Fractions", "it": "Frazioni"}
    assert curriculum_names.normalized_titles({"de": "Alt"}, german="Neu") == {"de": "Neu"}
    assert curriculum_names.normalized_titles("Brüche") == {}
    assert curriculum_names.missing_locales({"de": "Brüche", "it": "Frazioni"}) == ["en", "fr"]


def test_a_rows_own_name_comes_before_the_translation_table() -> None:
    row = {
        "unit_id": "brueche-u1",
        "topic_id": "brueche",
        "title": "Brüche verstehen",
        "titles": {"de": "Brüche verstehen", "en": "Fractions, understood"},
    }

    def name(locale: str) -> str | None:
        return curriculum_names.for_reader(locale, rows=[row]).name("brueche-u1")

    assert name("en") == "Fractions, understood"
    # A language the row does not name: the table, until the backfill names it.
    assert name("fr") == curriculum_translations.TITLE_TRANSLATIONS["brueche-u1"]["fr"]
    assert name("de") == "Brüche verstehen"
    # Without the table, the row's German name.
    unknown = {**row, "unit_id": "new-unit", "titles": {"de": "Neu", "en": "New"}}
    assert curriculum_names.for_reader("it", rows=[unknown]).name("new-unit") == "Neu"


def test_two_rows_of_one_lesson_each_give_the_languages_the_other_lacks() -> None:
    """The learning history: a progress row kept the German title it had then,
    and the lesson's row names it in the other languages."""
    kept = {"lesson_id": "brueche-l1", "title": "Brüche kürzen (damals)"}
    row = {"lesson_id": "brueche-l1", "title": "Brüche lesen", "titles": {"de": "Brüche lesen", "en": "Reading fractions"}}

    assert curriculum_names.for_reader("de", rows=[kept, row]).name("brueche-l1") == "Brüche kürzen (damals)"
    assert curriculum_names.for_reader("en", rows=[kept, row]).name("brueche-l1") == "Reading fractions"


def test_a_spelling_in_a_rows_language_resolves_to_its_unit() -> None:
    catalog = {
        "units": [{"id": "new-unit", "topicId": "brueche", "title": "Neuer Stern"}],
        "topics": [{"id": "brueche", "title": "Brüche"}],
    }
    row = {"unit_id": "new-unit", "title": "Neuer Stern", "titles": {"de": "Neuer Stern", "fr": "Nouvelle étoile"}}

    assert curriculum_names.for_reader("de", catalog=catalog, rows=[row]).resolve("Nouvelle étoile") == "new-unit"
    assert curriculum_names.for_reader("de", catalog=catalog).resolve("Nouvelle étoile") is None


# ── the seed ────────────────────────────────────────────────────────────────


def test_every_seeded_content_row_carries_the_names_readers_are_shown() -> None:
    rows = seed_practice.seed_rows(knowledge_base=seed_practice.KNOWLEDGE_BASE_LIVE)
    knowledge_base = {
        **{row["topic_id"]: row["titles"] for row in knowledge_base_catalog.topics()},
        **{row["unit_id"]: row["titles"] for row in knowledge_base_catalog.units()},
    }
    content = [row for row in rows if seed_practice.row_kind(row) in {"TOPIC", "UNIT", "LESSON"}]
    assert content
    for row in content:
        content_id = row.get("lesson_id") or row.get("unit_id") or row["topic_id"]
        expected = knowledge_base.get(content_id) or {
            "de": row["title"],
            **curriculum_translations.TITLE_TRANSLATIONS[content_id],
        }
        assert row["titles"] == expected, content_id
        assert row["titles"]["de"] == row["title"], content_id
        assert list(row["titles"]) == list(curriculum_names.LOCALES), content_id


# ── authoring, migrations and the publish projection ───────────────────────


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    return published.install_seeded_table(monkeypatch)


def _named_payload(**names: Any) -> dict[str, Any]:
    payload = published._payload(published._exercise(1))
    payload.pop("title")
    return {**payload, **names}


def _draft(payload: dict[str, Any]) -> dict[str, Any]:
    return curriculum_ops_service.create_lesson_draft(payload, published.OPERATOR)["lesson"]


def test_a_draft_holds_its_names_with_german_its_title(table: FakeTable) -> None:
    assert _draft(_named_payload(title="Brüche addieren", titles={**TITLES, "de": "anders"}))[
        "titles"
    ] == TITLES
    only_titles = _draft(_named_payload(titles=TITLES))
    assert only_titles["title"] == "Brüche addieren"
    assert only_titles["titles"] == TITLES
    assert "titles" not in _draft(_named_payload(title="Brüche addieren"))


def test_a_patch_renames_the_lesson_in_every_language_it_names(table: FakeTable) -> None:
    created = curriculum_ops_service.create_lesson_draft(_named_payload(titles=TITLES), published.OPERATOR)

    patched = curriculum_ops_service.patch_lesson_draft(
        LESSON_ID, created["versionId"], {"title": "Brüche zusammenzählen"}, published.OPERATOR
    )["lesson"]
    assert patched["titles"] == {**TITLES, "de": "Brüche zusammenzählen"}

    patched = curriculum_ops_service.patch_lesson_draft(
        LESSON_ID,
        created["versionId"],
        {"titles": {"de": "Brüche summieren", "en": "Summing fractions"}},
        published.OPERATOR,
    )["lesson"]
    assert patched["title"] == "Brüche summieren"
    assert patched["titles"] == {"de": "Brüche summieren", "en": "Summing fractions"}


def test_a_published_lesson_is_named_by_its_row_in_every_language(table: FakeTable) -> None:
    published._publish(_named_payload(titles=TITLES))

    row = table.rows[("PRACTICE", f"LESSON#{LESSON_ID}")]
    assert row["title"] == "Brüche addieren"
    assert row["titles"] == TITLES
    for locale, name in TITLES.items():
        catalog = curriculum_service.list_catalog(locale=locale, lesson_rows=[row])
        assert next(item for item in catalog["lessons"] if item["id"] == LESSON_ID)["title"] == name


def test_a_version_without_names_keeps_the_rows_while_its_german_name_is_the_same(
    table: FakeTable,
) -> None:
    first = published._publish(_named_payload(titles=TITLES))
    # A version written before #661: the German title alone.
    second = published._publish(published._payload(published._exercise(1), published._exercise(2)), first)
    assert table.rows[("PRACTICE", f"LESSON#{LESSON_ID}")]["titles"] == TITLES

    renamed = {**published._payload(published._exercise(1)), "title": "Brüche addieren üben"}
    published._publish(renamed, second)
    row = table.rows[("PRACTICE", f"LESSON#{LESSON_ID}")]
    assert row["title"] == "Brüche addieren üben"
    assert "titles" not in row


def _manifest(lesson: dict[str, Any]) -> dict[str, Any]:
    payload = published._payload(published._exercise(1))
    return {
        "source": {"sourceId": "test", "sourceVersion": "1"},
        "lessons": [
            {
                "publicLessonId": LESSON_ID,
                "lesson": {key: value for key, value in payload.items() if key != "exercises"} | lesson,
                "exercises": payload["exercises"],
            }
        ],
    }


def test_the_migration_dry_run_lists_the_lessons_a_language_does_not_name(table: FakeTable) -> None:
    partial = curriculum_migration_service.dry_run(
        _manifest({"titles": {"en": "Adding fractions"}}), published.OPERATOR
    )
    [row] = partial["rows"]
    assert row["lesson"]["titles"] == {"de": "Brüche addieren", "en": "Adding fractions"}
    assert row["missingTitleLocales"] == ["fr", "it"]
    assert partial["summary"]["missingTitles"] == 1
    # Not an error: the lesson is shown in German in those languages.
    assert partial["publishReady"] is True

    named = curriculum_migration_service.dry_run(_manifest({"titles": TITLES}), published.OPERATOR)
    assert named["rows"][0]["missingTitleLocales"] == []
    assert named["summary"]["missingTitles"] == 0


def test_a_manifest_without_names_normalizes_as_before(table: FakeTable) -> None:
    """Its migration id, and whether a row is a skip, do not change (#661)."""
    preview = curriculum_migration_service.dry_run(_manifest({}), published.OPERATOR)

    assert "titles" not in preview["rows"][0]["lesson"]
    assert preview["rows"][0]["missingTitleLocales"] == ["en", "fr", "it"]
