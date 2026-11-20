"""Recordings shaped the way browsers write them, built byte by byte (#477).

No real voice is in any of them: the audio payloads are filler (and, where a
test asks, a marker it then looks for everywhere a recording must not be).
What matters is the container around them, which `stoa.services.voice_audio`
reads the length from:

- `webm`: what Chrome's MediaRecorder writes - a Segment and Clusters of
  unknown size, no Duration, SimpleBlocks every `step` seconds.
- `ogg`: Firefox's Ogg Opus - OpusHead, OpusTags, then audio pages whose
  granule positions count 48 kHz samples after the pre-skip.
- `mp4`: Safari's AAC, either one movie with its durations in `mvhd`/`mdhd`
  or fragmented (`moof`/`traf`/`trun`, durations per sample, header ones 0).
- `wav`: what the client sends since #542 - RIFF/WAVE, plain PCM, by default
  16 kHz mono 16-bit, the one layout the transcription takes.

The model takes only the WAV (#542); the other three are what a browser's
`MediaRecorder` writes, kept to show they are refused.
"""

from __future__ import annotations

import struct

FILLER = b"\x00" * 40


# ── WebM ─────────────────────────────────────────────────────────────────────


def _ebml_size(size: int) -> bytes:
    return bytes([0x08]) + size.to_bytes(4, "big")  # 4-byte length vint


def _element(element_id: int, body: bytes) -> bytes:
    id_bytes = element_id.to_bytes((element_id.bit_length() + 7) // 8, "big")
    return id_bytes + _ebml_size(len(body)) + body


_UNKNOWN_SIZE = b"\x01\xff\xff\xff\xff\xff\xff\xff"


def webm(seconds: float, *, step: float = 0.5, payload: bytes = FILLER) -> bytes:
    header = _element(
        0x1A45DFA3,
        _element(0x4286, b"\x01") + _element(0x4282, b"webm"),
    )
    info = _element(0x1549A966, _element(0x2AD7B1, (1_000_000).to_bytes(3, "big")))
    tracks = _element(0x1654AE6B, _element(0xAE, _element(0x86, b"A_OPUS")))
    body = b""
    moments = []
    t = 0.0
    while t <= seconds + 1e-9:
        moments.append(round(t * 1000))
        t += step
    cluster_start = None
    for ms in moments:
        if cluster_start is None or ms - cluster_start > 5000:
            cluster_start = ms
            body += b"\x1f\x43\xb6\x75" + _UNKNOWN_SIZE
            body += _element(0xE7, cluster_start.to_bytes(4, "big"))
        block = b"\x81" + struct.pack(">h", ms - cluster_start) + b"\x80" + payload
        body += _element(0xA3, block)
    return header + b"\x18\x53\x80\x67" + _UNKNOWN_SIZE + info + tracks + body


# ── Ogg Opus ─────────────────────────────────────────────────────────────────


def _ogg_page(body: bytes, granule: int, sequence: int, header_type: int = 0) -> bytes:
    lacing = []
    remaining = len(body)
    while remaining >= 255:
        lacing.append(255)
        remaining -= 255
    lacing.append(remaining)
    return (
        b"OggS"
        + bytes([0, header_type])
        + struct.pack("<qII", granule, 0x5354_4F41, sequence)
        + b"\x00\x00\x00\x00"  # CRC: not checked by the reader
        + bytes([len(lacing)])
        + bytes(lacing)
        + body
    )


def ogg(seconds: float, *, pre_skip: int = 312, codec: bytes = b"OpusHead", payload: bytes = FILLER) -> bytes:
    head = codec + bytes([1, 1]) + struct.pack("<HIhB", pre_skip, 48_000, 0, 0)
    pages = [_ogg_page(head, 0, 0, 2), _ogg_page(b"OpusTags" + b"\x00" * 8, 0, 1)]
    total = pre_skip + round(seconds * 48_000)
    granule = pre_skip
    sequence = 2
    while granule < total:
        granule = min(total, granule + 48_000)
        pages.append(_ogg_page(payload, granule, sequence))
        sequence += 1
    return b"".join(pages)


# ── MP4 ──────────────────────────────────────────────────────────────────────


def _box(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", 8 + len(body)) + kind + body


def _full(kind: bytes, version: int, flags: int, body: bytes) -> bytes:
    return _box(kind, bytes([version]) + flags.to_bytes(3, "big") + body)


def _times(kind: bytes, scale: int, duration: int) -> bytes:
    return _full(kind, 0, 0, struct.pack(">IIII", 0, 0, scale, duration) + b"\x00" * 8)


def _trak(scale: int, duration: int) -> bytes:
    hdlr = _full(b"hdlr", 0, 0, b"\x00" * 4 + b"soun" + b"\x00" * 13)
    return _box(b"trak", _box(b"mdia", _times(b"mdhd", scale, duration) + hdlr))


def mp4(
    seconds: float,
    *,
    fragmented: bool = False,
    tracks: int = 1,
    payload: bytes = FILLER,
) -> bytes:
    scale = 44_100
    ftyp = _box(b"ftyp", b"isom" + b"\x00\x00\x02\x00" + b"isomiso2mp41")
    if not fragmented:
        units = round(seconds * scale)
        moov = _box(
            b"moov",
            _times(b"mvhd", 1000, round(seconds * 1000)) + _trak(scale, units) * tracks,
        )
        return ftyp + moov + _box(b"mdat", payload)
    trex = _full(b"trex", 0, 0, struct.pack(">IIIII", 1, 1, 0, 0, 0))
    moov = _box(
        b"moov",
        _times(b"mvhd", 1000, 0) + _trak(scale, 0) * tracks + _box(b"mvex", trex),
    )
    fragments = b""
    frame = 1024  # AAC samples per frame
    frames = round(seconds * scale / frame)
    done = 0
    while done < frames:
        count = min(43, frames - done)  # about a second per fragment
        tfhd = _full(b"tfhd", 0, 0x020000, struct.pack(">I", 1))
        tfdt = _full(b"tfdt", 1, 0, struct.pack(">Q", done * frame))
        trun = _full(
            b"trun", 0, 0x000300, struct.pack(">I", count) + struct.pack(">II", frame, 10) * count
        )
        fragments += _box(b"moof", _box(b"traf", tfhd + tfdt + trun)) + _box(b"mdat", payload)
        done += count
    return ftyp + moov + fragments


# ── WAV ──────────────────────────────────────────────────────────────────────


def wav(
    seconds: float,
    *,
    rate: int = 16_000,
    channels: int = 1,
    bits: int = 16,
    tag: int = 1,
    payload: bytes = FILLER,
    extra_chunk: bytes = b"",
) -> bytes:
    """A WAV of `seconds`, its samples `payload` repeated (and cut) to fill the data chunk."""
    block = channels * bits // 8
    size = round(seconds * rate) * block
    data = (payload * (size // max(len(payload), 1) + 1))[:size]
    fmt = struct.pack("<HHIIHH", tag, channels, rate, rate * block, block, bits)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt + extra_chunk
    chunks += b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks
