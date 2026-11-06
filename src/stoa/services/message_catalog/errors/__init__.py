"""The message a rule violation is sent with, one file per domain (#211).

Each key is `error.<code>` (`stoa.rule_violation.catalog_key`), the code being
the stable string a client compares. A domain that registers codes adds its
file here; `tests/test_error_catalog.py` fails for a registered code without
a key, a key missing a language, or a translation whose `{params}` differ.
"""

from stoa.services.message_catalog.errors import (
    account,
    adaptive_learning,
    ai_teacher_tools,
    ask_question,
    attachment,
    billing,
    help_request,
    moderation,
    notification,
    parent_link,
    practice,
    rate_limit,
    security,
    teacher_reply,
    validation,
)

_DOMAINS = (
    security,
    attachment,
    ask_question,
    validation,
    help_request,
    teacher_reply,
    parent_link,
    billing,
    account,
    practice,
    adaptive_learning,
    ai_teacher_tools,
    moderation,
    notification,
    rate_limit,
)


def _merge() -> dict[str, dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for domain in _DOMAINS:
        for key, variants in domain.TEXT.items():
            if not key.startswith("error."):
                raise RuntimeError(f"{domain.__name__}: {key!r} is not an error key")
            if key in merged:
                raise RuntimeError(f"{key!r} is defined twice in the error catalog")
            merged[key] = variants
    return merged


TEXT: dict[str, dict[str, str]] = _merge()
