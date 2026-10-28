import pytest

from stoa.services.teacher_reply_service import TeacherReplyValidationError, normalize_teacher_reply


def _paragraph(text):
    return {"version": 1, "blocks": [{"type": "paragraph", "text": text}]}


def _formula(latex):
    return {"version": 1, "blocks": [{"type": "formula", "latex": latex}]}


MATHS_AND_PROSE = [
    "0 < a < 1",
    "0<a<1",
    "wenn 0<a und a<1",
    "a <= b",
    "Set one = 1 first",
    "once = 2",
]
MARKUP = [
    "<script>alert(1)</script>",
    "<SCRIPT SRC=//x.example/x.js>",
    "<img src=x onerror=alert(1)>",
    '<a href="https://x.example">x</a>',
    "<a\nhref=https://x.example>x</a>",
    "<svg/onload=alert(1)>",
    "<details open ontoggle=alert(1)>",
    '<div title=">" onclick=alert(1)>',
]


@pytest.mark.parametrize("text", MATHS_AND_PROSE)
def test_maths_and_prose_are_not_html(text):
    assert normalize_teacher_reply(text, None)["teacher_response_rich"]["blocks"][0]["text"] == text
    assert normalize_teacher_reply(None, _paragraph(text))["teacher_response_rich"]["blocks"][0]["text"] == text


@pytest.mark.parametrize("latex", [r"\left< a \right>", r"\text{one} = 1", "0 < a < 1"])
def test_latex_in_formula_blocks_is_not_html(latex):
    assert normalize_teacher_reply(None, _formula(latex))["teacher_response_rich"]["blocks"][0]["latex"] == latex


@pytest.mark.parametrize("text", MARKUP)
def test_markup_is_refused_as_raw_html(text):
    for content, rich_content in ((text, None), (None, _paragraph(text)), (None, _formula(text))):
        with pytest.raises(TeacherReplyValidationError, match="unsafe raw HTML"):
            normalize_teacher_reply(content, rich_content)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("see private/student-1/image.png", "private markers"),
        ("key AKIAABCDEFGHIJKLMNOP", "private credentials"),
    ],
)
def test_private_marker_checks_are_unchanged(text, reason):
    with pytest.raises(TeacherReplyValidationError, match=reason):
        normalize_teacher_reply(text, None)
