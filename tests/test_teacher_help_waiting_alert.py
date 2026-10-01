"""#88: operations learn about a student nobody can help.

A request no teacher could be offered used to wait in silence: the sweep found
nobody, wrote nothing anyone watched, and tried again five minutes later. Past
thirty minutes (configurable) each sweep now logs one closed telemetry line for
it - the request id and the minutes waited, nothing about the student - which
an infra metric filter turns into a `stoa-alerts` alarm.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from fakes.dynamodb import FakeTable
import pytest

from stoa.config import settings
from stoa.services import teacher_dispatch_service

import test_chat_help_request_lifecycle as lifecycle
from test_chat_help_request_lifecycle import CREATED, REQUEST, STUDENT, TEACHER, _dispatch_to
from test_chat_help_waiting_and_withdraw import _nobody_available

EVENT = teacher_dispatch_service.TEACHER_HELP_WAITING_EVENT


@pytest.fixture
def table(monkeypatch) -> FakeTable:
    built = lifecycle.build_table(monkeypatch)
    lifecycle.keep_waiting(monkeypatch)
    monkeypatch.setattr(settings, "teacher_help_alert_after_seconds", 30 * 60)
    return built


def _after(minutes: int) -> str:
    return (datetime.fromisoformat(CREATED) + timedelta(minutes=minutes)).isoformat()


def _lines(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "stoa.private_telemetry" and EVENT in record.getMessage()
    ]


def _sweep(minutes: int) -> None:
    teacher_dispatch_service.reconcile_dispatches(now=_after(minutes))


def test_a_request_waiting_past_the_limit_with_nobody_to_offer_it_is_logged(
    table, caplog
) -> None:
    _nobody_available(table)
    with caplog.at_level(logging.INFO, logger="stoa.private_telemetry"):
        _sweep(31)
    [line] = _lines(caplog)
    assert line.startswith(f"event_category={EVENT}")
    assert f"correlation_id={REQUEST}" in line
    assert "wait_minutes=31" in line


def test_the_line_says_nothing_about_the_student(table, caplog) -> None:
    _nobody_available(table)
    with caplog.at_level(logging.INFO, logger="stoa.private_telemetry"):
        _sweep(31)
    [line] = _lines(caplog)
    assert STUDENT not in line
    assert "Step 2" not in line
    assert set(field.split("=", 1)[0] for field in line.split()) == {
        "event_category",
        "wait_minutes",
        "correlation_id",
    }


def test_a_request_inside_the_limit_is_not_logged(table, caplog) -> None:
    _nobody_available(table)
    with caplog.at_level(logging.INFO, logger="stoa.private_telemetry"):
        _sweep(29)
    assert _lines(caplog) == []


def test_a_request_offered_to_a_teacher_is_not_logged(table, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="stoa.private_telemetry"):
        _sweep(31)
    assert _lines(caplog) == []


def test_a_request_with_a_live_offer_is_not_logged(table, caplog) -> None:
    _dispatch_to(table, TEACHER)
    _nobody_available(table)
    with caplog.at_level(logging.INFO, logger="stoa.private_telemetry"):
        _sweep(31)
    assert _lines(caplog) == []


def test_every_sweep_logs_it_again_while_it_waits(table, caplog) -> None:
    # The alarm counts lines per period and SNS writes only when it changes
    # state, so a line each sweep keeps it raised without paging each time.
    _nobody_available(table)
    with caplog.at_level(logging.INFO, logger="stoa.private_telemetry"):
        _sweep(31)
        _sweep(36)
    assert len(_lines(caplog)) == 2


def test_the_limit_is_configurable(table, caplog, monkeypatch) -> None:
    monkeypatch.setattr(settings, "teacher_help_alert_after_seconds", 5 * 60)
    _nobody_available(table)
    with caplog.at_level(logging.INFO, logger="stoa.private_telemetry"):
        _sweep(6)
    assert len(_lines(caplog)) == 1


def test_a_withdrawn_request_is_not_logged(table, caplog) -> None:
    from test_chat_help_waiting_and_withdraw import _student, _withdraw

    _nobody_available(table)
    assert _withdraw(_student()).status_code == 200
    with caplog.at_level(logging.INFO, logger="stoa.private_telemetry"):
        _sweep(31)
    assert _lines(caplog) == []


def test_a_request_the_sweep_expires_is_not_logged(table, caplog, monkeypatch) -> None:
    monkeypatch.setattr(settings, "teacher_help_expiry_seconds", 60 * 60)
    _nobody_available(table)
    with caplog.at_level(logging.INFO, logger="stoa.private_telemetry"):
        _sweep(61)
    assert lifecycle._conv(table)["escalation_status"] == "expired"
    assert _lines(caplog) == []


def test_a_request_without_its_own_stamp_is_measured_from_finding_nobody(
    table, caplog
) -> None:
    _nobody_available(table)
    _sweep(1)  # records since when nobody could be found
    del lifecycle._conv(table)["escalated_at"]
    with caplog.at_level(logging.INFO, logger="stoa.private_telemetry"):
        _sweep(32)
    [line] = _lines(caplog)
    assert "wait_minutes=31" in line
