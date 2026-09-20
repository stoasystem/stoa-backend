"""Card 002 gap #12: the rate limiter's topology assumption, made explicit.

Per-source rate limiting is only per-source because `api.stoaedu.ch` is reached
straight from API Gateway, which overwrites the peer address with the caller's.
Put a CDN in front and every caller arrives from the same edge address: the limit
stops being one bucket per caller and becomes one switch for everybody — and until
this file existed, nothing in the suite would have gone red.

So the depth is declared (`trusted_proxy_hops`) rather than assumed, the declaration
is checked against the request instead of believed, and the collapse itself is
executable below.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from stoa.config import Settings, settings
from stoa.routers import auth
from stoa.services import rate_limit
from stoa.services.rate_limit import ProxyTopologyError, client_source_digest


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "stoa"

# The one module allowed to name a forwarding header in executable code. A second
# interpretation of these headers anywhere else is a second, undeclared topology
# assumption, which is exactly the shape of the bug this card recorded.
FORWARDING_HEADER_ALLOWLIST = {Path("services/rate_limit.py")}

SPOOFED_HEADERS = {
    "x-forwarded-for": "10.0.0.1, 10.0.0.2",
    "x-real-ip": "10.0.0.3",
    "true-client-ip": "10.0.0.4",
    "cf-connecting-ip": "10.0.0.5",
    "forwarded": "for=10.0.0.6",
}


class _StubRequest:
    def __init__(self, peer: str, headers: dict[str, str] | None = None) -> None:
        self.client = type("_Peer", (), {"host": peer})()
        self.headers = headers or {}


# ---------------------------------------------------------------------------
# The declared default: direct exposure, headers are noise
# ---------------------------------------------------------------------------


def test_出厂声明的是零层代理() -> None:
    assert settings.trusted_proxy_hops == 0
    assert Settings.model_fields["trusted_proxy_hops"].default == 0


def test_零层代理下任何转发头都不改变分桶() -> None:
    plain = client_source_digest(_StubRequest("198.51.100.7"), trusted_proxy_hops=0)

    for header, value in SPOOFED_HEADERS.items():
        spoofed = _StubRequest("198.51.100.7", {header: value})
        assert client_source_digest(spoofed, trusted_proxy_hops=0) == plain

    assert (
        client_source_digest(_StubRequest("198.51.100.7", SPOOFED_HEADERS), trusted_proxy_hops=0)
        == plain
    )


def test_每个转发头名都被这条判据覆盖() -> None:
    assert set(rate_limit.FORWARDING_HEADERS) == set(SPOOFED_HEADERS)


def test_阴性对照_不同的直连来源确实落在不同的桶() -> None:
    """Without this, a derivation that returned a constant would pass the test above."""
    first = client_source_digest(_StubRequest("198.51.100.7"), trusted_proxy_hops=0)
    second = client_source_digest(_StubRequest("203.0.113.9"), trusted_proxy_hops=0)

    assert first != second


# ---------------------------------------------------------------------------
# The collapse, and the knob that undoes it
# ---------------------------------------------------------------------------


def _through_one_edge(viewer: str) -> _StubRequest:
    """One request as it arrives once a CDN is put in front of API Gateway."""
    return _StubRequest("192.0.2.50", {"x-forwarded-for": f"{viewer}, 192.0.2.50"})


VIEWERS = ("198.51.100.7", "203.0.113.9", "192.0.2.200")


def test_挂上代理而不声明_三个访客塌成一个桶() -> None:
    buckets = {client_source_digest(_through_one_edge(v), trusted_proxy_hops=0) for v in VIEWERS}

    assert len(buckets) == 1


def test_声明一层代理后三个访客重新分开() -> None:
    buckets = {client_source_digest(_through_one_edge(v), trusted_proxy_hops=1) for v in VIEWERS}

    assert len(buckets) == 3
    for viewer in VIEWERS:
        assert client_source_digest(
            _through_one_edge(viewer), trusted_proxy_hops=1
        ) == client_source_digest(_StubRequest(viewer), trusted_proxy_hops=0)


def test_代理模式下链左侧的伪造项不改变分桶() -> None:
    honest = _StubRequest("192.0.2.50", {"x-forwarded-for": "198.51.100.7, 192.0.2.50"})
    padded = _StubRequest(
        "192.0.2.50", {"x-forwarded-for": "1.2.3.4, 5.6.7.8, 198.51.100.7, 192.0.2.50"}
    )

    assert client_source_digest(padded, trusted_proxy_hops=1) == client_source_digest(
        honest, trusted_proxy_hops=1
    )


# ---------------------------------------------------------------------------
# A declaration that does not match the request refuses rather than guesses
# ---------------------------------------------------------------------------


def test_声明了代理但链里没有它_拒绝() -> None:
    with pytest.raises(ProxyTopologyError):
        client_source_digest(_StubRequest("192.0.2.50"), trusted_proxy_hops=1)


def test_链太短装不下声明的层数_拒绝() -> None:
    request = _StubRequest("192.0.2.50", {"x-forwarded-for": "192.0.2.50"})

    with pytest.raises(ProxyTopologyError):
        client_source_digest(request, trusted_proxy_hops=2)


def test_链的末端不是观测到的对端_拒绝() -> None:
    request = _StubRequest("192.0.2.50", {"x-forwarded-for": "198.51.100.7, 198.51.100.8"})

    with pytest.raises(ProxyTopologyError):
        client_source_digest(request, trusted_proxy_hops=1)


def test_层数不是非负整数_拒绝() -> None:
    for bad in (-1, True, 1.0, "1"):
        with pytest.raises(ProxyTopologyError):
            client_source_digest(_StubRequest("192.0.2.50"), trusted_proxy_hops=bad)


def test_不传层数时用配置声明的那个值() -> None:
    assert client_source_digest(_StubRequest("198.51.100.7")) == client_source_digest(
        _StubRequest("198.51.100.7"), trusted_proxy_hops=settings.trusted_proxy_hops
    )


def test_配置拒绝负的代理层数() -> None:
    with pytest.raises(ValueError):
        Settings(trusted_proxy_hops=-1)


# ---------------------------------------------------------------------------
# The other per-source bucket in the service obeys the same rule
# ---------------------------------------------------------------------------


def test_邀请认领的分桶同样不读转发头() -> None:
    plain = auth._claim_source_digest(_StubRequest("198.51.100.7"))
    spoofed = auth._claim_source_digest(_StubRequest("198.51.100.7", SPOOFED_HEADERS))
    other = auth._claim_source_digest(_StubRequest("203.0.113.9"))

    assert spoofed == plain
    assert other != plain


# ---------------------------------------------------------------------------
# No second, undeclared place interprets these headers
# ---------------------------------------------------------------------------


def _non_docstring_literals(tree: ast.AST) -> list[str]:
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_源码里只有一处解释转发头() -> None:
    offenders: list[str] = []
    for module in sorted(SOURCE_ROOT.rglob("*.py")):
        relative = module.relative_to(SOURCE_ROOT)
        if relative in FORWARDING_HEADER_ALLOWLIST:
            continue
        literals = _non_docstring_literals(ast.parse(module.read_text(encoding="utf-8")))
        for literal in literals:
            lowered = literal.lower()
            if any(header in lowered for header in rate_limit.FORWARDING_HEADERS):
                offenders.append(f"{relative}: {literal!r}")

    assert not offenders, (
        "a forwarding header is read outside the declared source derivation: "
        f"{offenders}"
    )


def test_阴性对照_这条扫描确实看得见违例() -> None:
    """The sweep above only means something if a planted offender trips it."""
    planted = ast.parse('def f(request):\n    return request.headers["X-Forwarded-For"]\n')

    literals = [value.lower() for value in _non_docstring_literals(planted)]

    assert any(header in literal for literal in literals for header in rate_limit.FORWARDING_HEADERS)


def test_阴性对照_文档字符串里的提及不算违例() -> None:
    """auth.py explains the rule in prose; prose must not be read as a header read."""
    documented = ast.parse('def f():\n    """X-Forwarded-For is caller-controlled."""\n')

    assert _non_docstring_literals(documented) == []
