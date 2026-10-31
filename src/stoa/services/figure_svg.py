"""Figures an exercise may show: a small SVG drawing, checked against an allowlist.

A figure is drawn by the client straight into the page, so it is held to what a
diagram needs and nothing else: the shapes, text and arrow markers the exercise
figures use, with presentation attributes. No script, no event handler, no link,
no external reference, no embedded document, no CSS. A figure that strays from
the allowlist is refused when it is authored, not repaired: a silently cleaned
drawing could lose the line the answer depends on.

`figure_issues` says what is wrong with one; an empty list means it may be stored
and shown as written.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

#: The longest figure an exercise may carry, in characters.
MAX_FIGURE_LENGTH = 32_000

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
ELEMENTS = frozenset({
    "svg", "g", "defs", "marker", "title", "desc",
    "line", "polyline", "polygon", "rect", "circle", "ellipse", "path",
    "text", "tspan",
})
ATTRIBUTES = frozenset({
    "xmlns", "viewBox", "width", "height", "preserveAspectRatio", "role", "aria-label",
    "id", "transform",
    "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "d", "points", "dx", "dy",
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity",
    "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "stroke-dashoffset", "opacity",
    "font-size", "font-family", "font-weight", "font-style", "text-anchor", "dominant-baseline",
    "markerWidth", "markerHeight", "refX", "refY", "orient", "markerUnits",
    "marker-start", "marker-mid", "marker-end",
})
#: The only reference a figure may make: to a marker of its own, written just so.
#: A paint or marker attribute is read as CSS, which reads `URL(` and the escape
#: `\75 rl(` as `url(` too and fetches whatever follows (#168): any value that
#: mentions `url(` in any case or spacing, or holds a backslash at all, must be
#: exactly this, pointing at an id the figure has.
_LOCAL_REFERENCE = re.compile(r"url\(#([A-Za-z_][\w.-]*)\)")
_MENTIONS_URL = re.compile(r"url\s*\(", re.IGNORECASE)
_FORBIDDEN_TEXT = re.compile(r"<!DOCTYPE|<!ENTITY|<\?|javascript:|data:|expression\(", re.IGNORECASE)


def _name(tag: str) -> tuple[str, str]:
    if tag.startswith("{"):
        namespace, _, local = tag[1:].partition("}")
        return namespace, local
    return "", tag


def _refers_out(attr: str, value: str, ids: set[str]) -> bool:
    """Whether a value may be read as anything but itself or a reference to the figure's own ids."""
    # A name is read out, never parsed as CSS: a backslash there is just text.
    if attr == "aria-label" or ("\\" not in value and _MENTIONS_URL.search(value) is None):
        return False
    local = _LOCAL_REFERENCE.fullmatch(value.strip())
    return local is None or local.group(1) not in ids


def figure_issues(svg: object) -> list[str]:
    """What keeps this figure from being shown as written; empty when nothing does."""
    if not isinstance(svg, str) or not svg.strip():
        return ["A figure must be SVG text."]
    if len(svg) > MAX_FIGURE_LENGTH:
        return [f"A figure is at most {MAX_FIGURE_LENGTH} characters."]
    if _FORBIDDEN_TEXT.search(svg):
        return ["A figure may hold no document type, entity, processing instruction or script URL."]
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return ["A figure must be well-formed SVG."]
    issues: list[str] = []
    ids = {element.attrib["id"] for element in root.iter() if "id" in element.attrib}
    if _name(root.tag) != (SVG_NAMESPACE, "svg"):
        issues.append("A figure's root must be an svg element in the SVG namespace.")
    for element in root.iter():
        namespace, tag = _name(element.tag)
        if namespace != SVG_NAMESPACE or tag not in ELEMENTS:
            issues.append(f"Element '{tag}' is not allowed in a figure.")
            continue
        for raw_name, value in element.attrib.items():
            attr_namespace, attr = _name(raw_name)
            if attr_namespace or attr not in ATTRIBUTES:
                issues.append(f"Attribute '{attr}' is not allowed in a figure.")
            elif _refers_out(attr, value, ids):
                issues.append(f"Attribute '{attr}' may only refer to a marker of the figure itself.")
    return list(dict.fromkeys(issues))


def has_text(svg: str) -> bool:
    """Whether the figure carries words a reader could need in their own language."""
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return False
    return any(
        re.search(r"[^\W\d_]{2,}", "".join(element.itertext()))
        for element in root.iter()
        if _name(element.tag)[1] in {"text", "tspan"}
    )
