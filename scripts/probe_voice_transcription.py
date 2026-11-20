#!/usr/bin/env python3
"""Run a folder of real recordings through the voice transcription, as the endpoint would (#478).

Before voice questions go live, Voxtral is retested on real voices: a child's,
Swiss German, background noise (#469 measured only Polly's synthetic speech).
This takes every file in a folder, checks it with the endpoint's own
`check_recording` (container, size, length), sends the ones it takes to the
same `VoxtralTranscriber` the endpoint uses, in the same region, and prints one
Markdown table row per file: language, container, length, the format sent,
milliseconds the model took, outcome, how far what was heard is from what was
said, what was heard and what was said.

- What was said is read from `<name>.txt` beside the recording, if there is one.
  Write it as the transcription should read: for Swiss German, the words as
  spoken; for a dictated formula, the form you expect back (`x² + 3x = 0` or
  `x hoch zwei plus drei x`, whichever is wanted).
- The language is the first part of the file name that is a language code
  (`gsw-kind-laerm.webm` is Swiss German): de, gsw, fr, it, en, rm.
- "Word error" is the share of the words said that would have to change to turn
  what was heard into them, ignoring case and punctuation: 0% is verbatim. A
  translation shows as a word error of 100% or more.

Voxtral takes only mp3 and wav (measured 2026-11-20, #542), so the WebM, Ogg and
MP4 the endpoint takes today are all refused. `--send-as wav` converts each
recording the endpoint would take with the local `ffmpeg` (16 kHz mono) before
sending it, which measures how well the model hears the voice whatever #542
settles. Without it, each recording is sent exactly as the endpoint sends it.
Files the endpoint would not take (a `.wav` voice memo, say) are reported with
the endpoint's error code and never sent.

It calls Bedrock for real (and is billed for it) on whatever AWS session it is
given; it is for an operator on SSO, never for CI. No student is involved, no
table is touched and nothing is written but `--out`, if given.

    python scripts/probe_voice_transcription.py RECORDINGS_DIR --profile PROFILE [--send-as wav] [--out FILE]
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from stoa import config  # noqa: E402
from stoa.services import voice_audio  # noqa: E402
from stoa.services.transcription import TranscriptionFailed, VoxtralTranscriber  # noqa: E402
from stoa.services.voice_transcription import VoiceQuestionViolation, check_recording  # noqa: E402

# Beside a recording, not one: what was said, and notes.
_NOT_RECORDINGS = frozenset({".txt", ".md"})
# What a browser declares for each container; the endpoint requires the two to agree.
_DECLARED = {
    voice_audio.Container.WEBM: "audio/webm",
    voice_audio.Container.OGG: "audio/ogg",
    voice_audio.Container.MP4: "audio/mp4",
}
LANGUAGES = ("de", "gsw", "fr", "it", "en", "rm")


class SendAs(StrEnum):
    """A format Voxtral takes, as Bedrock's `AudioBlock.format` names it."""

    WAV = "wav"
    MP3 = "mp3"


# The recording at this path, converted to this format.
Convert = Callable[[Path, SendAs], bytes]


@dataclass(frozen=True)
class Row:
    name: str
    language: str
    container: str
    seconds: float | None
    sent_as: str
    elapsed_ms: int | None
    outcome: str
    word_error: float | None
    heard: str
    said: str


def _said(recording: Path) -> str:
    sidecar = recording.with_suffix(".txt")
    return sidecar.read_text(encoding="utf-8").strip() if sidecar.is_file() else ""


def language(recording: Path) -> str:
    """The first part of the file name that is a language code, or ''."""
    for part in re.split(r"[-_. ]+", recording.stem.lower()):
        if part in LANGUAGES:
            return part
    return ""


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def word_error(heard: str, said: str) -> float | None:
    """Word edits from what was heard to what was said, over the words said; None without them."""
    target, got = _words(said), _words(heard)
    if not target:
        return None
    previous = list(range(len(got) + 1))
    for i, word in enumerate(target, start=1):
        current = [i]
        for j, other in enumerate(got, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (word != other)))
        previous = current
    return previous[-1] / len(target)


def ffmpeg(path: Path, send_as: SendAs) -> bytes:
    """The recording as 16 kHz mono `send_as`, by the local ffmpeg."""
    binary = shutil.which("ffmpeg")
    if binary is None:
        raise SystemExit("--send-as needs ffmpeg on PATH (winget install Gyan.FFmpeg)")
    codec = ["-c:a", "libmp3lame", "-b:a", "64k"] if send_as is SendAs.MP3 else ["-c:a", "pcm_s16le"]
    command = [binary, "-nostdin", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "16000"]
    return subprocess.run(
        [*command, *codec, "-f", send_as.value, "-"], check=True, capture_output=True
    ).stdout


def _probe(
    path: Path, transcriber: VoxtralTranscriber, send_as: SendAs | None, convert: Convert
) -> Row:
    audio = path.read_bytes()
    said = _said(path)
    spoken = language(path)
    container = voice_audio.sniffed_container(audio)
    content_type = _DECLARED[container] if container else "application/octet-stream"
    seconds: float | None = None
    try:
        recording = check_recording(audio, content_type)
    except VoiceQuestionViolation as exc:
        if container is not None:
            try:
                seconds = voice_audio.read(audio, content_type).seconds
            except ValueError:
                pass
        kept = container.value if container else ""
        return Row(path.name, spoken, kept, seconds, "", None, exc.code.value, None, "", said)
    if send_as is None:
        sent, sent_format = audio, recording.container
    else:
        # The transcriber reads only `.value` from it: Bedrock's `AudioBlock.format`.
        sent, sent_format = convert(path, send_as), cast(voice_audio.Container, send_as)
    started = time.perf_counter()
    try:
        heard = transcriber.transcribe(sent, sent_format)
        outcome = "transcribed" if heard else "nothing heard"
    except TranscriptionFailed as exc:
        heard = ""
        outcome = f"{'refused' if exc.refused else 'failed'} ({exc.reason})"
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return Row(
        path.name,
        spoken,
        recording.container.value,
        recording.seconds,
        sent_format.value,
        elapsed_ms,
        outcome,
        word_error(heard, said) if heard else None,
        heard,
        said,
    )


def run(
    folder: Path,
    *,
    transcriber: VoxtralTranscriber | None = None,
    send_as: SendAs | None = None,
    convert: Convert = ffmpeg,
) -> list[Row]:
    """One row per recording in `folder`, in name order."""
    transcriber = transcriber or VoxtralTranscriber()
    files = sorted(
        path for path in folder.iterdir() if path.is_file() and path.suffix.lower() not in _NOT_RECORDINGS
    )
    return [_probe(path, transcriber, send_as, convert) for path in files]


def _cell(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


def markdown(rows: list[Row], *, model_id: str) -> str:
    lines = [
        f"Model `{model_id}` in `{config.settings().voice_transcription_region}`, "
        f"{len(rows)} recording(s).",
        "",
        "| File | Language | Container | Seconds | Sent as | Model ms | Outcome | Word error | Heard | Said |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        seconds = f"{row.seconds:.1f}" if row.seconds is not None else ""
        elapsed = str(row.elapsed_ms) if row.elapsed_ms is not None else ""
        error = f"{row.word_error:.0%}" if row.word_error is not None else ""
        cells = [
            row.name,
            row.language,
            row.container,
            seconds,
            row.sent_as,
            elapsed,
            row.outcome,
            error,
            row.heard,
            row.said,
        ]
        lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path, help="folder of recordings, with an optional <name>.txt each")
    parser.add_argument("--profile", help="AWS profile to call Bedrock with (an SSO profile)")
    parser.add_argument(
        "--send-as",
        type=SendAs,
        choices=list(SendAs),
        help="convert each recording with ffmpeg and send it in this format (Voxtral takes only these)",
    )
    parser.add_argument("--out", type=Path, help="also write the table to this file")
    args = parser.parse_args(argv)
    if not args.folder.is_dir():
        parser.error(f"not a folder: {args.folder}")
    if args.profile:
        os.environ["AWS_PROFILE"] = args.profile

    transcriber = VoxtralTranscriber()
    rows = run(args.folder, transcriber=transcriber, send_as=args.send_as)
    table = markdown(rows, model_id=transcriber.model_id)
    print(table)
    if args.out:
        args.out.write_text(table + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
