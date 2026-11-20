"""The gates of 模型调用 (#435 item 11, #439).

1. Only the Bedrock adapter talks to Bedrock about a model call: nowhere else
   in `src/stoa` calls `invoke_model*` or `count_tokens`, or names them.
2. Who pays for a call is not listed by hand: it follows from whether the call
   was made with an admission hook (`model_call.CostClass`).
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
import re
import time

import pytest

from stoa.services import ask_answer, model_call, report_service
from stoa.services.ask_question import _admission
from stoa.services.model_call.fake import FakeAdapter, Reply

_SOURCE = Path(__file__).resolve().parents[1] / "src" / "stoa"
_ADAPTER = _SOURCE / "services" / "model_call" / "bedrock.py"
_PROVIDER_OPERATION = re.compile(r"invoke_model|count_tokens")

_ANSWER = {"steps": ["Zähler und Nenner teilen"], "answer": "So kürzt man."}


def _sources() -> list[Path]:
    return sorted(_SOURCE.rglob("*.py"))


# ── Only the adapter reaches Bedrock ─────────────────────────────────────────


def test_only_the_bedrock_adapter_calls_invoke_model_or_count_tokens() -> None:
    callers: list[str] = []
    for path in _sources():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and _PROVIDER_OPERATION.match(node.func.attr)
                and path != _ADAPTER
            ):
                callers.append(f"{path.relative_to(_SOURCE)}:{node.lineno} {node.func.attr}")

    assert callers == [], "only model_call/bedrock.py may call Bedrock for a model call"


def test_no_other_source_names_them_at_all() -> None:
    """As `grep -rn "count_tokens\\|invoke_model" src/stoa` reads it: a getattr,
    a string or a comment naming the operations counts as much as a call."""
    naming = [
        f"{path.relative_to(_SOURCE)}:{number}"
        for path in _sources()
        if path != _ADAPTER
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _PROVIDER_OPERATION.search(line)
    ]

    assert naming == []


def test_the_adapter_is_where_both_operations_are_called() -> None:
    called = {
        node.func.attr
        for node in ast.walk(ast.parse(_ADAPTER.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert {"count_tokens", "invoke_model_with_response_stream"} <= called
    # The buffered call is gone (#435 item 6): only the stream is sent.
    assert "invoke_model" not in called


# ── The cost class follows from the admission hook ───────────────────────────


def _call(model: FakeAdapter, *, admission: model_call.AdmissionHook | None) -> model_call.Result:
    model_call.install(model)
    return model_call.call(
        system="Answer the question.",
        messages=[{"role": "user", "content": "Wie kürzt man 6/8?"}],
        tool=ask_answer.answer_tool(star_map=False),
        max_tokens=2048,
        temperature=ask_answer.ANSWER_TEMPERATURE,
        deadline=time.monotonic() + 90,
        admission=admission,
    )


def _admit(_input_tokens: int, _max_output_tokens: int) -> model_call.Admit:
    return model_call.Admit()


@pytest.mark.parametrize(
    ("admission", "cost_class"),
    [
        (_admit, model_call.CostClass.USER_ALLOWANCE),
        (None, model_call.CostClass.PROVIDER_COST_ONLY),
    ],
)
def test_a_paid_reply_is_charged_as_its_admission_hook_says(
    admission: model_call.AdmissionHook | None, cost_class: model_call.CostClass
) -> None:
    answered = _call(FakeAdapter(_ANSWER), admission=admission)
    cut_off = _call(
        FakeAdapter(Reply(input=_ANSWER, stop_reason="max_tokens")), admission=admission
    )

    assert isinstance(answered, model_call.Answered)
    assert answered.usage.cost_class is cost_class
    assert isinstance(cut_off, model_call.PaidUnusable)
    assert cut_off.usage.cost_class is cost_class


def test_an_ask_answer_is_charged_to_the_allowance_only_when_admitted() -> None:
    admitted = ask_answer.provider_result(
        _call(FakeAdapter(_ANSWER), admission=_admit), effect_id="effect-admitted"
    )
    unadmitted = ask_answer.provider_result(
        _call(FakeAdapter(_ANSWER), admission=None), effect_id="effect-unadmitted"
    )

    assert admitted.invocation_class is model_call.CostClass.USER_ALLOWANCE
    assert unadmitted.invocation_class is model_call.CostClass.PROVIDER_COST_ONLY
    # An answer no hook admitted cannot settle an allowance reservation.
    with pytest.raises(_admission.AdmissionError):
        _admission.UsageEvidence.from_provider(unadmitted, effect_id="effect-unadmitted")


def test_the_weekly_report_is_paid_at_provider_cost_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    model_call.install(FakeAdapter({"summary": "Eine ruhige Woche."}))
    payload = {
        "student": {"name": "Synthetic Student", "grade": 5},
        "week": {"start": "2026-11-09", "end": "2026-11-15"},
        "metrics": {},
        "activities": [],
    }

    with caplog.at_level(logging.INFO, logger=report_service.logger.name):
        report_service.generate_weekly_report_content(payload)

    assert "cost_class=provider_cost_only" in caplog.text
