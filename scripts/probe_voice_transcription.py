#!/usr/bin/env python3
"""Run a folder of real recordings through the voice transcription, as the endpoint would (#478).

Before voice questions go live, Voxtral is retested on real voices: a child's,
Swiss German, background noise (#469 measured only Polly's synthetic speech).
This takes every file in a folder, checks it with the endpoint's own
`check_recording` (container, size, length), sends the ones it takes to the
same `VoxtralTranscriber` the endpoint uses, in the same region, and prints one
Markdown table row per file: container, length, milliseconds the model took,
outcome, what was heard and what was said.

What was said is read from `<name>.txt` beside the recording, if there is one.
Files the endpoint would not take (a `.wav` voice memo, say) are reported with
the endpoint's error code and never sent, so convert them to WebM/Ogg (Opus) or
MP4 (AAC) first if they are to be tested.

It calls Bedrock for real (and is billed for it) on whatever AWS session it is
given; it is for an operator on SSO, never for CI. No student is involved, no
table is touched and nothing is written but `--out`, if given.

    python scripts/probe_voice_transcription.py RECORDINGS_DIR --profile PROFILE [--out FILE]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True)
class Row:
    name: str
    container: str
    seconds: float | None
    elapsed_ms: int | None
    outcome: str
    heard: str
    said: str


def _said(recording: Path) -> str:
    sidecar = recording.with_suffix(".txt")
    return sidecar.read_text(encoding="utf-8").strip() if sidecar.is_file() else ""


def _probe(path: Path, transcriber: VoxtralTranscriber) -> Row:
    audio = path.read_bytes()
    said = _said(path)
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
        return Row(path.name, container.value if container else "", seconds, None, exc.code.value, "", said)
    started = time.perf_counter()
    try:
        heard = transcriber.transcribe(audio, recording.container)
        outcome = "transcribed" if heard else "nothing heard"
    except TranscriptionFailed as exc:
        heard = ""
        outcome = f"{'refused' if exc.refused else 'failed'} ({exc.reason})"
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return Row(path.name, recording.container.value, recording.seconds, elapsed_ms, outcome, heard, said)


def run(folder: Path, *, transcriber: VoxtralTranscriber | None = None) -> list[Row]:
    """One row per recording in `folder`, in name order."""
    transcriber = transcriber or VoxtralTranscriber()
    files = sorted(
        path for path in folder.iterdir() if path.is_file() and path.suffix.lower() not in _NOT_RECORDINGS
    )
    return [_probe(path, transcriber) for path in files]


def _cell(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


def markdown(rows: list[Row], *, model_id: str) -> str:
    lines = [
        f"Model `{model_id}` in `{config.settings().voice_transcription_region}`, "
        f"{len(rows)} recording(s).",
        "",
        "| File | Container | Seconds | Model ms | Outcome | Heard | Said |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        seconds = f"{row.seconds:.1f}" if row.seconds is not None else ""
        elapsed = str(row.elapsed_ms) if row.elapsed_ms is not None else ""
        cells = [row.name, row.container, seconds, elapsed, row.outcome, row.heard, row.said]
        lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path, help="folder of recordings, with an optional <name>.txt each")
    parser.add_argument("--profile", help="AWS profile to call Bedrock with (an SSO profile)")
    parser.add_argument("--out", type=Path, help="also write the table to this file")
    args = parser.parse_args(argv)
    if not args.folder.is_dir():
        parser.error(f"not a folder: {args.folder}")
    if args.profile:
        os.environ["AWS_PROFILE"] = args.profile

    transcriber = VoxtralTranscriber()
    table = markdown(run(args.folder, transcriber=transcriber), model_id=transcriber.model_id)
    print(table)
    if args.out:
        args.out.write_text(table + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
