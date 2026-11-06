"""What is wrong with a draft lesson, by code (#112).

The validation report of the curriculum console (`curriculum_ops_service.
_validation_issues`) lists each problem with the field it is in. The problem is
an `Issue`: a stable `code` and the `params` its sentence needs. The console is
four-language, so it translates by code; `message` is the English sentence,
kept for a client that does not know the code yet.

The sentences are in the message catalog under `curriculum_issue.<code>`
(`message_catalog.curriculum_issues`). This is a report, not a refusal: an
issue is never raised. A draft with a blocking issue is refused with the rule
violation `validation_failed` (`curriculum_errors`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from stoa.services import message_catalog

#: The language of `message`, the fallback for a client that does not translate.
FALLBACK_LOCALE = "en"


class IssueCode(StrEnum):
    # The lesson.
    LESSON_FIELD_MISSING = "lesson_field_missing"
    UNIT_MISSING = "unit_missing"
    UNIT_UNKNOWN = "unit_unknown"
    TOPIC_NOT_THE_UNITS = "topic_not_the_units"
    SUBJECT_NOT_THE_UNITS = "subject_not_the_units"
    PREREQUISITE_UNKNOWN = "prerequisite_unknown"
    PREREQUISITE_UNRELATED = "prerequisite_unrelated"
    PREREQUISITE_CYCLE = "prerequisite_cycle"
    EXERCISE_REQUIRED = "exercise_required"
    # An exercise.
    EXERCISE_ID_REPEATED = "exercise_id_repeated"
    EXERCISE_FIELD_MISSING = "exercise_field_missing"
    OPTIONS_WITHOUT_CHOICE = "options_without_choice"
    TOO_FEW_OPTIONS = "too_few_options"
    OPTIONS_READ_THE_SAME = "options_read_the_same"
    ANSWER_NOT_AN_OPTION = "answer_not_an_option"
    SKILLS_NOT_A_LIST = "skills_not_a_list"
    SKILL_UNKNOWN = "skill_unknown"
    SKILL_IN_ANOTHER_UNIT = "skill_in_another_unit"
    # A figure (`figure_svg`) or the option figures (`exercise_localization`).
    FIGURE_NOT_TEXT = "figure_not_text"
    FIGURE_TOO_LONG = "figure_too_long"
    FIGURE_FORBIDDEN_MARKUP = "figure_forbidden_markup"
    FIGURE_MALFORMED = "figure_malformed"
    FIGURE_ROOT_NOT_SVG = "figure_root_not_svg"
    FIGURE_ELEMENT_NOT_ALLOWED = "figure_element_not_allowed"
    FIGURE_ATTRIBUTE_NOT_ALLOWED = "figure_attribute_not_allowed"
    FIGURE_REFERENCE_OUTSIDE = "figure_reference_outside"
    OPTION_FIGURES_MISMATCH = "option_figures_mismatch"
    # A translation (`exercise_localization`).
    TRANSLATIONS_NOT_A_MAP = "translations_not_a_map"
    TRANSLATION_LOCALE_UNSUPPORTED = "translation_locale_unsupported"
    TRANSLATION_PROMPT_MISSING = "translation_prompt_missing"
    TRANSLATION_TOO_LONG = "translation_too_long"
    TRANSLATION_OPTIONS_MISMATCH = "translation_options_mismatch"
    TRANSLATION_ANSWER_NOT_THE_OPTION = "translation_answer_not_the_option"
    TRANSLATION_ANSWER_MISSING = "translation_answer_missing"
    ACCEPTED_ANSWERS_OUT_OF_BOUNDS = "accepted_answers_out_of_bounds"


def catalog_key(code: IssueCode | str) -> str:
    """The message catalog key of an issue code (`curriculum_issue.<code>`)."""
    return f"curriculum_issue.{code}"


@dataclass(frozen=True, slots=True)
class Issue:
    """One problem: its code and the values its sentence names.

    Hashable, so the same problem found twice is reported once.
    """

    code: IssueCode
    params: tuple[tuple[str, str], ...] = ()

    @classmethod
    def of(cls, code: IssueCode, **params: object) -> Issue:
        return cls(code, tuple(sorted((name, str(value)) for name, value in params.items())))

    @property
    def values(self) -> dict[str, str]:
        return dict(self.params)

    def message(self, locale: str = FALLBACK_LOCALE) -> str:
        return message_catalog.text(catalog_key(self.code), locale, **self.values)
