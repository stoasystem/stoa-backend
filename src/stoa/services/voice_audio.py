"""What a voice question's recording is, and how long it lasts, read from its bytes (#477).

Browsers record in one of three containers, and each is handed to the model as
it came, never transcoded:

- WebM (Opus): Chrome, Edge and Firefox's `MediaRecorder`. Bedrock format `webm`.
- Ogg (Opus): Firefox when asked for `audio/ogg`. Bedrock format `ogg`.
- MP4 (AAC): Safari's `MediaRecorder`, and Chrome when asked for `audio/mp4`.
  Bedrock format `mp4`.

The container is told by its first bytes, and the declared `Content-Type` has to
name the same one. The length is read from the container itself, never taken
from the client: the last block's timestamp in WebM (MediaRecorder writes no
duration there), the last page's granule position in Ogg, the movie or
fragment durations in MP4. A recording whose length cannot be read is refused
as unreadable rather than guessed at.

Nothing here keeps or logs the bytes.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import StrEnum


class Container(StrEnum):
    """A container the transcription takes; the value is its Bedrock `AudioBlock.format`."""

    WEBM = "webm"
    OGG = "ogg"
    MP4 = "mp4"


# The media types each container may be declared as, parameters (`;codecs=...`) aside.
DECLARED_TYPES: dict[Container, frozenset[str]] = {
    Container.WEBM: frozenset({"audio/webm", "video/webm"}),
    Container.OGG: frozenset({"audio/ogg", "application/ogg"}),
    Container.MP4: frozenset({"audio/mp4", "audio/m4a", "audio/x-m4a", "video/mp4"}),
}


@dataclass(frozen=True, slots=True)
class Recording:
    container: Container
    seconds: float


class UnsupportedFormat(ValueError):
    """The declared type, or the bytes, are not a container the transcription takes."""


class Unreadable(ValueError):
    """The bytes claim a container the transcription takes, but its length cannot be read."""


def media_type(content_type: str | None) -> str:
    """`audio/webm;codecs=opus` -> `audio/webm`."""
    return str(content_type or "").split(";", 1)[0].strip().lower()


def declared_container(content_type: str | None) -> Container:
    declared = media_type(content_type)
    for container, names in DECLARED_TYPES.items():
        if declared in names:
            return container
    raise UnsupportedFormat("declared type is not a supported recording")


def sniffed_container(audio: bytes) -> Container | None:
    if audio[:4] == b"\x1a\x45\xdf\xa3":
        return Container.WEBM
    if audio[:4] == b"OggS":
        return Container.OGG
    if audio[4:8] == b"ftyp":
        return Container.MP4
    return None


def read(audio: bytes, content_type: str | None) -> Recording:
    """The container and length of `audio`, declared as `content_type`."""
    declared = declared_container(content_type)
    sniffed = sniffed_container(audio)
    if sniffed is None:
        raise UnsupportedFormat("bytes are not a supported container")
    if sniffed is not declared:
        raise UnsupportedFormat("bytes are not the declared container")
    seconds = _LENGTH_READERS[sniffed](audio)
    if not seconds > 0:
        raise Unreadable("recording has no length")
    return Recording(sniffed, seconds)


# ── WebM / Matroska ──────────────────────────────────────────────────────────

_EBML = 0x1A45DFA3
_SEGMENT = 0x18538067
_INFO = 0x1549A966
_TIMECODE_SCALE = 0x2AD7B1
_DURATION = 0x4489
_CLUSTER = 0x1F43B675
_CLUSTER_TIMECODE = 0xE7
_SIMPLE_BLOCK = 0xA3
_BLOCK_GROUP = 0xA0
_BLOCK = 0xA1
# Entered rather than skipped: their children are read where they stand. A
# Segment and a Cluster from MediaRecorder have an unknown size, so they could
# not be skipped anyway.
_WEBM_CONTAINERS = frozenset({_SEGMENT, _INFO, _CLUSTER, _BLOCK_GROUP})


def _vint(data: bytes, offset: int, *, keep_marker: bool) -> tuple[int, int, bool]:
    """An EBML variable-length integer at `offset`: value, length, and whether all ones."""
    if offset >= len(data):
        raise Unreadable("truncated element")
    first = data[offset]
    length = 1
    mask = 0x80
    while length <= 8 and not first & mask:
        mask >>= 1
        length += 1
    if length > 8 or offset + length > len(data):
        raise Unreadable("bad element header")
    value = first if keep_marker else first & (mask - 1)
    for byte in data[offset + 1 : offset + length]:
        value = (value << 8) | byte
    all_ones = not keep_marker and value == (1 << (7 * length)) - 1
    return value, length, all_ones


def _uint(data: bytes) -> int:
    return int.from_bytes(data, "big") if data else 0


def _webm_seconds(data: bytes) -> float:
    scale = 1_000_000  # nanoseconds per timecode tick, Matroska's default
    declared: float | None = None
    cluster_time: int | None = None
    last_block: int | None = None
    offset = 0
    first = True
    while offset < len(data):
        element, id_length, _ = _vint(data, offset, keep_marker=True)
        size, size_length, unknown = _vint(data, offset + id_length, keep_marker=False)
        start = offset + id_length + size_length
        if first and element != _EBML:
            raise Unreadable("not an EBML document")
        first = False
        if element in _WEBM_CONTAINERS:
            offset = start
            continue
        if unknown or start + size > len(data):
            raise Unreadable("element runs past the recording")
        body = data[start : start + size]
        if element == _TIMECODE_SCALE:
            scale = _uint(body) or scale
        elif element == _DURATION and size in (4, 8):
            declared = struct.unpack(">f" if size == 4 else ">d", body)[0]
        elif element == _CLUSTER_TIMECODE:
            cluster_time = _uint(body)
        elif element in (_SIMPLE_BLOCK, _BLOCK):
            if cluster_time is None:
                raise Unreadable("block outside a cluster")
            _, track_length, _ = _vint(body, 0, keep_marker=False)
            if len(body) < track_length + 2:
                raise Unreadable("short block")
            relative = struct.unpack(">h", body[track_length : track_length + 2])[0]
            moment = cluster_time + relative
            last_block = moment if last_block is None else max(last_block, moment)
        offset = start + size
    ticks = max(declared or 0.0, float(last_block or 0))
    if last_block is None and not declared:
        raise Unreadable("no audio blocks")
    return ticks * scale / 1_000_000_000


# ── Ogg (Opus) ───────────────────────────────────────────────────────────────

_OPUS_RATE = 48_000  # Opus granule positions always count 48 kHz samples


def _ogg_seconds(data: bytes) -> float:
    offset = 0
    pre_skip: int | None = None
    last_granule = -1
    while offset < len(data):
        if data[offset : offset + 4] != b"OggS" or offset + 27 > len(data):
            raise Unreadable("bad Ogg page")
        granule = struct.unpack("<q", data[offset + 6 : offset + 14])[0]
        segments = data[offset + 26]
        table_end = offset + 27 + segments
        if table_end > len(data):
            raise Unreadable("truncated Ogg page")
        body_length = sum(data[offset + 27 : table_end])
        body_end = table_end + body_length
        if body_end > len(data):
            raise Unreadable("truncated Ogg page")
        if pre_skip is None:
            body = data[table_end:body_end]
            if body[:8] != b"OpusHead" or len(body) < 12:
                raise UnsupportedFormat("Ogg recording is not Opus")
            pre_skip = struct.unpack("<H", body[10:12])[0]
        if granule >= 0:
            last_granule = max(last_granule, granule)
        offset = body_end
    if pre_skip is None or last_granule <= 0:
        raise Unreadable("no Opus audio")
    return max(last_granule - pre_skip, 0) / _OPUS_RATE


# ── MP4 ──────────────────────────────────────────────────────────────────────

_MP4_CONTAINERS = frozenset({b"moov", b"trak", b"mdia", b"minf", b"stbl", b"mvex", b"moof", b"traf"})
_UNKNOWN_32 = 0xFFFFFFFF
_UNKNOWN_64 = 0xFFFFFFFFFFFFFFFF


@dataclass(slots=True)
class _Mp4:
    movie_scale: int = 0
    movie_duration: int = 0
    track_scale: int = 0
    track_duration: int = 0
    tracks: int = 0
    default_duration: int = 0  # trex
    fragment_end: int = 0  # in the track's timescale
    traf_base: int | None = None
    traf_default: int = 0
    traf_sum: int = 0


def _times(body: bytes) -> tuple[int, int]:
    """(timescale, duration) of an `mvhd` or `mdhd` box body."""
    if not body:
        raise Unreadable("empty header box")
    if body[0] == 1:
        if len(body) < 32:
            raise Unreadable("short header box")
        scale = struct.unpack(">I", body[20:24])[0]
        duration = struct.unpack(">Q", body[24:32])[0]
        return scale, 0 if duration == _UNKNOWN_64 else duration
    if len(body) < 20:
        raise Unreadable("short header box")
    scale, duration = struct.unpack(">II", body[12:20])
    return scale, 0 if duration == _UNKNOWN_32 else duration


def _close_traf(state: _Mp4) -> None:
    if state.traf_base is None and state.traf_sum == 0:
        return
    start = state.traf_base if state.traf_base is not None else state.fragment_end
    state.fragment_end = max(state.fragment_end, start + state.traf_sum)
    state.traf_base = None
    state.traf_default = 0
    state.traf_sum = 0


def _trun(body: bytes, default: int) -> int:
    if len(body) < 8:
        raise Unreadable("short trun")
    flags = int.from_bytes(body[1:4], "big")
    count = struct.unpack(">I", body[4:8])[0]
    offset = 8 + (4 if flags & 0x1 else 0) + (4 if flags & 0x4 else 0)
    per_sample = sum(4 for bit in (0x100, 0x200, 0x400, 0x800) if flags & bit)
    if not flags & 0x100:
        return count * default
    if offset + count * per_sample > len(body):
        raise Unreadable("short trun")
    total = 0
    for _ in range(count):
        total += struct.unpack(">I", body[offset : offset + 4])[0]
        offset += per_sample
    return total


def _walk_mp4(data: bytes, start: int, end: int, state: _Mp4) -> None:
    offset = start
    while offset < end:
        if offset + 8 > end:
            raise Unreadable("truncated box")
        size, kind = struct.unpack(">I4s", data[offset : offset + 8])
        header = 8
        if size == 1:
            if offset + 16 > end:
                raise Unreadable("truncated box")
            size = struct.unpack(">Q", data[offset + 8 : offset + 16])[0]
            header = 16
        elif size == 0:
            size = end - offset
        if size < header or offset + size > end:
            raise Unreadable("box runs past the recording")
        body_start, box_end = offset + header, offset + size
        body = data[body_start:box_end]
        if kind == b"trak":
            state.tracks += 1
        if kind == b"traf":
            _close_traf(state)
        if kind in _MP4_CONTAINERS:
            _walk_mp4(data, body_start, box_end, state)
            if kind == b"traf":
                _close_traf(state)
        elif kind == b"mvhd":
            state.movie_scale, state.movie_duration = _times(body)
        elif kind == b"mdhd":
            state.track_scale, state.track_duration = _times(body)
        elif kind == b"trex" and len(body) >= 16:
            state.default_duration = struct.unpack(">I", body[12:16])[0]
        elif kind == b"tfhd" and len(body) >= 8:
            flags = int.from_bytes(body[1:4], "big")
            cursor = 8 + (8 if flags & 0x1 else 0) + (4 if flags & 0x2 else 0)
            if flags & 0x8 and len(body) >= cursor + 4:
                state.traf_default = struct.unpack(">I", body[cursor : cursor + 4])[0]
        elif kind == b"tfdt" and len(body) >= 8:
            state.traf_base = (
                struct.unpack(">Q", body[4:12])[0] if body[0] == 1 and len(body) >= 12
                else struct.unpack(">I", body[4:8])[0]
            )
        elif kind == b"trun":
            state.traf_sum += _trun(body, state.traf_default or state.default_duration)
        offset = box_end


def _mp4_seconds(data: bytes) -> float:
    state = _Mp4()
    _walk_mp4(data, 0, len(data), state)
    if state.tracks != 1:
        raise Unreadable("an MP4 recording carries exactly one track")
    candidates = [0.0]
    if state.movie_scale:
        candidates.append(state.movie_duration / state.movie_scale)
    if state.track_scale:
        candidates.append(state.track_duration / state.track_scale)
        candidates.append(state.fragment_end / state.track_scale)
    return max(candidates)


_LENGTH_READERS = {
    Container.WEBM: _webm_seconds,
    Container.OGG: _ogg_seconds,
    Container.MP4: _mp4_seconds,
}
