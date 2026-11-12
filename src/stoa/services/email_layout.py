"""One frame for every email STOA sends (#374).

An email is a title, a greeting and a list of blocks; this module wraps them in
the STOA frame - logo, white card, footer with the company line - and derives
the plain-text part from the same HTML, so the two never drift apart.

Only mail-client-safe markup is written: tables for layout, inline styles, no
external CSS, web fonts or scripts. Every piece of text that reaches a block is
escaped here; callers hand in plain text, never markup.

A notification email's unsubscribe line belongs in the footer. It is added at
send time (the weekly report is stored before it is sent), so the footer ends
with `FOOTER_MARK` and `email_unsubscribe.with_footer` inserts there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html import escape
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from stoa import config
from stoa.services import locale_service, message_catalog

ZURICH = ZoneInfo("Europe/Zurich")
FOOTER_MARK = "<!--stoa:footer-end-->"
_TEXT_SKIP = 'data-text-part="skip"'

# The palette is the logo's: a deep red on warm white.
_INK = "#2b2523"
_MUTED = "#6b625e"
_FAINT = "#8a817c"
_BRAND = "#7a1f2b"
_BRAND_DARK = "#5c1620"
_PAGE = "#f4f2ef"
_FOOT = "#faf8f5"
_LINE = "#eee8e1"
_FONT = "Helvetica,Arial,sans-serif"


@dataclass(frozen=True, slots=True)
class Paragraph:
    text: str
    small: bool = False


@dataclass(frozen=True, slots=True)
class LabeledParagraph:
    """A bold label followed by text on the same line, e.g. a teacher's note."""

    label: str
    text: str


@dataclass(frozen=True, slots=True)
class Action:
    """The one button an email asks the reader to press, with its link spelled out below."""

    label: str
    url: str
    # The language of the "copy this link" line; by default the email's own.
    locale: str | None = None


@dataclass(frozen=True, slots=True)
class Code:
    """A one-time code, set large so it can be read and typed."""

    value: str


@dataclass(frozen=True, slots=True)
class Subheading:
    text: str


@dataclass(frozen=True, slots=True)
class Bullets:
    items: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Items:
    """Titled lines: each a bold title and a short text."""

    items: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Link:
    """A plain link, for a secondary destination that is not the email's main action."""

    label: str
    url: str


Block = Paragraph | LabeledParagraph | Action | Code | Subheading | Bullets | Items | Link


@dataclass(frozen=True, slots=True)
class Rendered:
    subject: str
    html: str
    text: str


def _lang(locale: str | None) -> str:
    try:
        return locale_service.normalize_locale(locale)
    except ValueError:
        return locale_service.DEFAULT_LOCALE


def _copy(key: str, lang: str, **values: object) -> str:
    return message_catalog.text(f"email.common.{key}", lang, **values)


def greeting(full_name: str | None, locale: str | None) -> str:
    """"Guten Tag Anna Muster" with a name, a nameless greeting without one."""
    lang = _lang(locale)
    name = str(full_name or "").strip()
    if name:
        return _copy("greeting", lang, name=name)
    return _copy("greeting_anonymous", lang)


_MONTHS = {
    "de": ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
           "September", "Oktober", "November", "Dezember"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"),
    "fr": ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre"),
    "it": ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
           "agosto", "settembre", "ottobre", "novembre", "dicembre"),
}


def format_datetime(value: str | datetime, locale: str | None) -> str:
    """A moment as people in Switzerland read it: Zurich time, words for the month.

    "13. November 2026, 14:50" in German. A value that is not an ISO timestamp is
    returned as it came, so a malformed field costs the formatting, not the email.
    """
    lang = _lang(locale)
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(ZURICH)
    month = _MONTHS[lang][local.month - 1]
    day = f"{local.day}." if lang == "de" else str(local.day)
    return f"{day} {month} {local.year}, {local:%H:%M}"


def format_date(value: str | date, locale: str | None) -> str:
    """A calendar day in words for the month: "1. Juni 2026" in German.

    A value that is not an ISO date comes back as it came.
    """
    lang = _lang(locale)
    if isinstance(value, date):
        day = value
    else:
        try:
            day = date.fromisoformat(str(value)[:10])
        except ValueError:
            return str(value)
    month = _MONTHS[lang][day.month - 1]
    prefix = f"{day.day}." if lang == "de" else str(day.day)
    return f"{prefix} {month} {day.year}"


def _p(
    text: str, *, size: int = 16, color: str = _INK, margin: str = "0 0 14px", text_part: bool = True
) -> str:
    # `text_part=False` keeps a paragraph out of the plain-text part, where it would repeat.
    skip = "" if text_part else f" {_TEXT_SKIP}"
    return (
        f'<p{skip} style="margin:{margin};font-size:{size}px;line-height:1.6;color:{color};">'
        f"{text}</p>"
    )


def _lines(text: str) -> str:
    """Escape text, keeping its line breaks."""
    return "<br>".join(escape(line) for line in str(text).split("\n"))


def _block(block: Block, lang: str) -> str:
    match block:
        case Paragraph(text=text, small=True):
            return _p(_lines(text), size=14, color=_MUTED)
        case Paragraph(text=text):
            return _p(_lines(text))
        case LabeledParagraph(label=label, text=text):
            return _p(f"<strong>{escape(label)}</strong> {_lines(text)}")
        case Subheading(text=text):
            return (
                f'<h2 style="margin:22px 0 10px;font-size:17px;line-height:1.35;'
                f'font-weight:700;color:{_BRAND_DARK};">{escape(text)}</h2>'
            )
        case Bullets(items=items):
            if not items:
                return ""
            rows = "".join(
                f'<li style="margin:0 0 6px;">{escape(str(item))}</li>' for item in items
            )
            return (
                f'<ul style="margin:0 0 14px;padding-left:22px;font-size:16px;'
                f'line-height:1.6;color:{_INK};">{rows}</ul>'
            )
        case Items(items=items):
            if not items:
                return ""
            rows = "".join(
                f'<li style="margin:0 0 8px;"><strong>{escape(str(title))}</strong>'
                + (f": {escape(str(text))}" if str(text or "").strip() else "")
                + "</li>"
                for title, text in items
            )
            return (
                f'<ul style="margin:0 0 14px;padding-left:22px;font-size:16px;'
                f'line-height:1.6;color:{_INK};">{rows}</ul>'
            )
        case Code(value=value):
            return (
                f'<p style="margin:6px 0 20px;"><span style="display:inline-block;'
                f"padding:12px 22px;border-radius:8px;background:{_PAGE};"
                f"border:1px solid {_LINE};font-family:Menlo,Consolas,monospace;"
                f'font-size:28px;letter-spacing:6px;font-weight:700;color:{_BRAND_DARK};">'
                f"{escape(value)}</span></p>"
            )
        case Action(label=label, url=url, locale=own):
            href = escape(url, quote=True)
            fallback = _copy("link_fallback", _lang(own) if own else lang)
            return (
                '<table role="presentation" cellpadding="0" cellspacing="0" '
                'style="margin:6px 0 22px;"><tr>'
                f'<td style="border-radius:8px;background:{_BRAND};">'
                f'<a href="{href}" style="display:inline-block;padding:13px 26px;'
                f"font-family:{_FONT};font-size:16px;font-weight:700;color:#ffffff;"
                f'text-decoration:none;border-radius:8px;">{escape(label)}</a>'
                "</td></tr></table>"
                + _p(
                    f"{escape(fallback)}<br>"
                    f'<a href="{href}" style="color:{_BRAND};word-break:break-all;">'
                    f"{escape(url)}</a>",
                    size=13,
                    color=_FAINT,
                    margin="0 0 22px",
                    text_part=False,
                )
            )
        case Link(label=label, url=url):
            return _p(
                f'<a href="{escape(url, quote=True)}" style="color:{_BRAND};">{escape(label)}</a>'
            )
    raise TypeError(f"not an email block: {block!r}")


def _frame(
    *, subject: str, title: str, body: str, lang: str, tagline: str, reason: str
) -> str:
    settings = config.settings()
    return f"""<!doctype html>
<html lang="{escape(lang, quote=True)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{escape(subject)}</title>
</head>
<body style="margin:0;padding:0;background:{_PAGE};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_PAGE};padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:12px;border:1px solid #e6e1da;">
<tr><td style="padding:28px 36px 8px;">
<img src="{escape(settings.email_logo_url, quote=True)}" width="132" alt="STOA" style="display:block;border:0;height:auto;">
</td></tr>
<tr><td style="padding:16px 36px 0;font-family:{_FONT};color:{_INK};">
<h1 style="margin:0 0 18px;font-size:22px;line-height:1.3;font-weight:700;color:{_BRAND_DARK};">{escape(title)}</h1>
{body}
</td></tr>
<tr><td style="padding:18px 36px 24px;background:{_FOOT};border-top:1px solid {_LINE};border-radius:0 0 12px 12px;font-family:{_FONT};font-size:12px;line-height:1.6;color:{_FAINT};">
<strong style="color:{_BRAND_DARK};">STOA</strong> · {escape(tagline)}<br>
Zürich · <a href="mailto:info@stoaedu.ch" style="color:{_FAINT};">info@stoaedu.ch</a> · <a href="https://stoaedu.ch" style="color:{_FAINT};">stoaedu.ch</a>
{reason}{FOOTER_MARK}
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _section_body(
    greeting: str | None, blocks: list[Block] | tuple[Block, ...], lang: str, questions: bool
) -> str:
    body = "".join(_block(block, lang) for block in blocks)
    if greeting:
        body = _p(escape(greeting)) + body
    if questions:
        body += _p(escape(_copy("questions", lang)), margin="8px 0 4px")
    return body + _p(_lines(_copy("signoff", lang)), margin="0 0 28px")


def _reason(text: str | None) -> str:
    return _p(escape(text), size=12, color=_FAINT, margin="8px 0 0") if text else ""


def render(
    *,
    subject: str,
    title: str,
    greeting: str | None,
    blocks: list[Block] | tuple[Block, ...],
    locale: str | None,
    footer_reason: str | None,
    questions: bool = True,
) -> Rendered:
    """One email in the STOA frame, as HTML and plain text.

    `footer_reason` says why the reader gets this email; a notification email
    leaves it out, since its unsubscribe line says the same and is added at
    send time. `questions` adds "reply to this email" above the sign-off.
    """
    lang = _lang(locale)
    html = _frame(
        subject=subject,
        title=title,
        body=_section_body(greeting, blocks, lang, questions),
        lang=lang,
        tagline=_copy("tagline", lang),
        reason=_reason(footer_reason),
    )
    return Rendered(subject=subject, html=html, text=to_text(html))


# The order a reader in Switzerland expects: the national languages, then English.
ALL_LOCALES: tuple[str, ...] = ("de", "fr", "it", "en")
LANGUAGE_NAMES = {"de": "Deutsch", "fr": "Français", "it": "Italiano", "en": "English"}


@dataclass(frozen=True, slots=True)
class Section:
    """One language's part of an email written in several (#415)."""

    locale: str
    greeting: str | None
    blocks: tuple[Block, ...]
    footer_reason: str | None = None


def render_multilingual(
    *, subject: str, title: str, sections: list[Section] | tuple[Section, ...]
) -> Rendered:
    """One email that says the same thing in several languages, one after the other.

    For a reader whose language STOA does not know yet. Each section is headed by
    its language's own name and carries its own greeting, sign-off and, in the
    footer, its own reason; the frame around them is drawn once.
    """
    if not sections:
        raise ValueError("a multilingual email needs at least one section")
    names = " · ".join(LANGUAGE_NAMES.get(_lang(s.locale), s.locale) for s in sections)
    parts = [_p(escape(names), size=13, color=_FAINT, margin="0 0 18px")]
    for index, section in enumerate(sections):
        lang = _lang(section.locale)
        rule = f"border-top:1px solid {_LINE};padding-top:18px;" if index else ""
        parts.append(
            f'<div lang="{escape(lang, quote=True)}" style="{rule}">'
            + _block(Subheading(LANGUAGE_NAMES.get(lang, lang)), lang)
            + _section_body(section.greeting, section.blocks, lang, True)
            + "</div>"
        )
    first = _lang(sections[0].locale)
    html = _frame(
        subject=subject,
        title=title,
        body="".join(parts),
        lang=first,
        tagline=_copy("tagline", first),
        reason="".join(_reason(s.footer_reason) for s in sections),
    )
    return Rendered(subject=subject, html=html, text=to_text(html))


class _TextWriter(HTMLParser):
    """HTML to readable plain text: paragraphs as blank lines, links as "label: url"."""

    _BREAKS = {"p", "h1", "h2", "ul", "table", "tr", "div"}
    _HIDDEN = {"head", "style", "script", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        # The element whose content stays out of the text, and how deep inside it we are.
        self._hidden_tag: str | None = None
        self._hidden_depth = 0
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._hidden_tag is not None:
            self._hidden_depth += tag == self._hidden_tag
            return
        if tag in self._HIDDEN or (tag == "p" and dict(attrs).get("data-text-part") == "skip"):
            self._hidden_tag, self._hidden_depth = tag, 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "a":
            self._href = dict(attrs).get("href")
            self._link_text = []
        elif tag in self._BREAKS:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if self._hidden_tag is not None:
            if tag == self._hidden_tag:
                self._hidden_depth -= 1
                if not self._hidden_depth:
                    self._hidden_tag = None
            return
        if tag == "a":
            label = "".join(self._link_text).strip()
            href = self._href or ""
            if href.startswith("mailto:"):
                href = href[len("mailto:"):]
            if href and label and label in href:
                self.parts.append(href)
            elif href:
                self.parts.append(f"{label}: {href}" if label else href)
            else:
                self.parts.append(label)
            self._href = None
        elif tag in self._BREAKS:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self._hidden_tag is not None:
            return
        if self._href is not None:
            self._link_text.append(data)
        else:
            self.parts.append(data)


def to_text(html: str) -> str:
    """The plain-text part of an email, read off its HTML."""
    writer = _TextWriter()
    writer.feed(html)
    writer.close()
    text = "".join(writer.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"
