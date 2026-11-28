"""A best-effort notification that fails says so: stoasystem/stoa-backend#79.

`create_event_safe` swallowed every exception and logged nothing, so if
notifications ever failed in production nobody would know. It still never
raises, but it now records which event failed and why, without content.
"""

from __future__ import annotations

import logging

from stoa.services.notifications import _bell


def test_a_failed_best_effort_notification_is_logged_not_raised(monkeypatch, caplog):
    monkeypatch.setattr(_bell, "_best_effort_disabled", lambda: False)

    def refuse(**_kwargs):
        raise RuntimeError("conditional account lifecycle conflict")

    monkeypatch.setattr(_bell, "create_event", refuse)

    with caplog.at_level(logging.WARNING, logger=_bell.logger.name):
        result = _bell.create_event_safe(
            recipient_id="student-79",
            event_type="teacher_reply",
            title="Teacher replied",
            summary="A private summary",
        )

    assert result is None
    (record,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert "teacher_reply" in record.getMessage()
    assert "RuntimeError" in record.getMessage()
    assert "private summary" not in record.getMessage()
