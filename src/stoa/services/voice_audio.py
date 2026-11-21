"""What a voice question's recording is, and how long it lasts, read from its bytes (#477, #542).

Voxtral takes only mp3 and wav (measured on the account 2026-11-20, #542): the
WebM, Ogg and MP4 a browser's `MediaRecorder` writes are refused. So the client
records PCM itself and sends one format, handed to the model as it came:

- WAV: a RIFF/WAVE file, plain PCM (format tag 1), 16 kHz, one channel, 16-bit
  samples. Bedrock format `wav`. 32,000 bytes a second, so a minute is 1.92 MB.

Anything else is unsupported: another container, or a WAV in another rate,
channel count, sample size or encoding (which would make the size limit mean a
different length). The format is told by the first bytes, and the declared
`Content-Type` has to name it. The length is the `data` chunk's size over the
byte rate, read from the file itself, never taken from the client. A WAV whose
chunks run past its end, or that has no `fmt ` before its `data`, is refused as
unreadable rather than guessed at.

Nothing here keeps or logs the bytes.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class Container(StrEnum):
    """A format the transcription takes; the value is its Bedrock `AudioBlock.format`."""

    WAV = "wav"


# The media types each format may be declared as, parameters aside.
DECLARED_TYPES: dict[Container, frozenset[str]] = {
    Container.WAV: frozenset({"audio/wav", "audio/wave", "audio/x-wav", "audio/vnd.wave"}),
}

SAMPLE_RATE: Final = 16_000
CHANNELS: Final = 1
BITS_PER_SAMPLE: Final = 16
BYTES_PER_SECOND: Final = SAMPLE_RATE * CHANNELS * BITS_PER_SAMPLE // 8

_PCM: Final = 1


@dataclass(frozen=True, slots=True)
class Recording:
    container: Container
    seconds: float


class UnsupportedFormat(ValueError):
    """The declared type, or the bytes, are not a format the transcription takes."""


class Unreadable(ValueError):
    """The bytes claim a format the transcription takes, but its length cannot be read."""


def media_type(content_type: str | None) -> str:
    """`audio/wav; codecs=1` -> `audio/wav`."""
    return str(content_type or "").split(";", 1)[0].strip().lower()


def declared_container(content_type: str | None) -> Container:
    declared = media_type(content_type)
    for container, names in DECLARED_TYPES.items():
        if declared in names:
            return container
    raise UnsupportedFormat("declared type is not a supported recording")


def sniffed_container(audio: bytes) -> Container | None:
    if audio[:4] == b"RIFF" and audio[8:12] == b"WAVE":
        return Container.WAV
    return None


def read(audio: bytes, content_type: str | None) -> Recording:
    """The format and length of `audio`, declared as `content_type`."""
    declared = declared_container(content_type)
    sniffed = sniffed_container(audio)
    if sniffed is None:
        raise UnsupportedFormat("bytes are not a supported format")
    if sniffed is not declared:
        raise UnsupportedFormat("bytes are not the declared format")
    seconds = _wav_seconds(audio)
    if not seconds > 0:
        raise Unreadable("recording has no length")
    return Recording(sniffed, seconds)


def _wav_seconds(data: bytes) -> float:
    """The `data` chunk's length in seconds, once `fmt ` says it is the one PCM layout taken."""
    offset = 12
    format_seen = False
    while offset + 8 <= len(data):
        kind, size = struct.unpack("<4sI", data[offset : offset + 8])
        body_start = offset + 8
        if body_start + size > len(data):
            raise Unreadable("chunk runs past the recording")
        if kind == b"fmt ":
            _check_format(data[body_start : body_start + size])
            format_seen = True
        elif kind == b"data":
            if not format_seen:
                raise Unreadable("data before its format")
            if size % (CHANNELS * BITS_PER_SAMPLE // 8):
                raise Unreadable("data is not whole samples")
            return size / BYTES_PER_SECOND
        offset = body_start + size + (size & 1)  # chunks are padded to an even length
    raise Unreadable("no data chunk")


def _check_format(body: bytes) -> None:
    if len(body) < 16:
        raise Unreadable("short fmt chunk")
    tag, channels, rate, byte_rate, block_align, bits = struct.unpack("<HHIIHH", body[:16])
    if (tag, channels, rate, bits) != (_PCM, CHANNELS, SAMPLE_RATE, BITS_PER_SAMPLE):
        raise UnsupportedFormat("WAV is not 16 kHz mono 16-bit PCM")
    if (byte_rate, block_align) != (BYTES_PER_SECOND, CHANNELS * BITS_PER_SAMPLE // 8):
        raise Unreadable("fmt chunk contradicts itself")
