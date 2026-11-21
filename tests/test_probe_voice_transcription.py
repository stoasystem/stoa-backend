"""#478: the real-recording retest runs each file the way the endpoint would.

`scripts/probe_voice_transcription.py` reads a folder of recordings, checks each
one with the endpoint's own `check_recording`, sends the ones it takes to the
transcriber and reports language, length, time taken and what was heard next to
what was said (`<name>.txt`). These tests run it against the Converse double;
the real run is the operator's, on their SSO session.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from fakes import recordings
from fakes.converse import FakeConverse, client_error
from scripts import probe_voice_transcription as probe
from stoa import aws
from stoa.services import voice_audio


@pytest.fixture(autouse=True)
def _no_installed_clients():
    yield
    aws.install(None)


def _folder(tmp_path: Path) -> Path:
    folder = tmp_path / "recordings"
    folder.mkdir()
    (folder / "01-kind-gsw-laerm.wav").write_bytes(recordings.wav(6))
    (folder / "01-kind-gsw-laerm.txt").write_text("Wie viel isch drü mal vier?\n", encoding="utf-8")
    (folder / "02-fr.m4a").write_bytes(recordings.mp4(4))
    (folder / "03-voice-memo-44k.wav").write_bytes(recordings.wav(3, rate=44_100))
    (folder / "04-too-long.wav").write_bytes(recordings.wav(62))
    (folder / "notes.md").write_text("not a recording", encoding="utf-8")
    return folder


def test_each_recording_is_checked_timed_and_set_next_to_what_was_said(tmp_path: Path) -> None:
    voxtral = FakeConverse("Wie viel isch drü mal vier?")
    aws.install({aws.Kind.VOICE_TRANSCRIPTION: voxtral})

    rows = probe.run(_folder(tmp_path))

    assert [row.name for row in rows] == [
        "01-kind-gsw-laerm.wav",
        "02-fr.m4a",
        "03-voice-memo-44k.wav",
        "04-too-long.wav",
    ]
    gsw, fr, memo, too_long = rows
    assert (gsw.language, gsw.recorded_as, gsw.sent_as, gsw.outcome, gsw.heard, gsw.said) == (
        "gsw",
        "wav",
        "wav",
        "transcribed",
        "Wie viel isch drü mal vier?",
        "Wie viel isch drü mal vier?",
    )
    assert gsw.seconds == pytest.approx(6)
    assert gsw.word_error == 0
    assert gsw.elapsed_ms is not None and gsw.elapsed_ms >= 0
    # Only the one the endpoint would take reaches the model, sent as the endpoint sends it.
    assert [r["messages"][0]["content"][0]["audio"]["format"] for r in voxtral.requests] == ["wav"]
    assert (fr.language, fr.recorded_as, fr.sent_as, fr.outcome, fr.elapsed_ms) == (
        "fr",
        "m4a",
        "",
        "voice_recording_unsupported",
        None,
    )
    assert (memo.outcome, memo.elapsed_ms) == ("voice_recording_unsupported", None)
    assert (too_long.outcome, too_long.elapsed_ms) == ("voice_recording_too_long", None)
    assert too_long.seconds == pytest.approx(62)


def test_send_as_wav_converts_every_file_then_checks_it_as_the_endpoint_would(tmp_path: Path) -> None:
    """A phone's or browser's recording is measured as the client's WAV would arrive (#542)."""
    voxtral = FakeConverse("a", "b", "c")
    aws.install({aws.Kind.VOICE_TRANSCRIPTION: voxtral})
    converted: list[tuple[str, probe.SendAs]] = []

    def convert(path: Path, send_as: probe.SendAs) -> bytes:
        converted.append((path.name, send_as))
        return recordings.wav(62 if "too-long" in path.name else 2, payload=path.name.encode())

    rows = probe.run(_folder(tmp_path), send_as=probe.SendAs.WAV, convert=convert)

    assert [name for name, _ in converted] == [
        "01-kind-gsw-laerm.wav",
        "02-fr.m4a",
        "03-voice-memo-44k.wav",
        "04-too-long.wav",
    ]
    assert {send_as for _, send_as in converted} == {"wav"}
    assert [r["messages"][0]["content"][0]["audio"]["format"] for r in voxtral.requests] == ["wav"] * 3
    gsw, fr, memo, too_long = rows
    assert (fr.recorded_as, fr.sent_as, fr.outcome) == ("m4a", "wav", "transcribed")
    assert (memo.sent_as, memo.outcome) == ("wav", "transcribed")
    # Converting does not get round the endpoint's own limits.
    assert too_long.outcome == "voice_recording_too_long"


def test_a_refusal_is_reported_as_the_one_the_alarm_counts(tmp_path: Path) -> None:
    folder = tmp_path / "one"
    folder.mkdir()
    (folder / "a.wav").write_bytes(recordings.wav(3))
    aws.install(
        {aws.Kind.VOICE_TRANSCRIPTION: FakeConverse(client_error("ValidationException"))}
    )

    [row] = probe.run(folder)

    assert row.outcome == "refused (ValidationException)"
    assert row.heard == ""


def test_the_report_is_one_markdown_table_row_per_recording(tmp_path: Path) -> None:
    aws.install({aws.Kind.VOICE_TRANSCRIPTION: FakeConverse("x | y\nzwei")})
    folder = tmp_path / "one"
    folder.mkdir()
    (folder / "a.wav").write_bytes(recordings.wav(3))

    table = probe.markdown(probe.run(folder), model_id="mistral.voxtral-small-24b-2507")

    lines = table.splitlines()
    assert "mistral.voxtral-small-24b-2507" in lines[0]
    header = next(i for i, line in enumerate(lines) if line.startswith("| File"))
    assert lines[header + 1].startswith("|---")
    [row] = lines[header + 2 :]
    assert row.startswith("| a.wav |  | wav | 3.0 | wav |")
    # A pipe or line break in what was heard cannot break the table.
    assert "x \\| y zwei" in row


@pytest.mark.parametrize(
    ("heard", "said", "error"),
    [
        ("Wie viel isch drü mal vier?", "wie viel isch drü mal vier", 0.0),
        ("Wie viel ist drei mal vier?", "Wie viel isch drü mal vier?", 2 / 6),
        ("How much is three times four?", "Combien font trois fois quatre ?", 6 / 5),
        ("x² + 3x = 0", "x² + 3x = 0", 0.0),
        ("anything", "", None),
    ],
    ids=["verbatim", "standard-german-for-swiss", "translated", "formula", "nothing-said"],
)
def test_word_error_is_how_far_what_was_heard_is_from_what_was_said(
    heard: str, said: str, error: float | None
) -> None:
    assert probe.word_error(heard, said) == (pytest.approx(error) if error is not None else None)


def test_the_language_is_read_from_the_file_name() -> None:
    assert probe.language(Path("01-kind-gsw-laerm.webm")) == "gsw"
    assert probe.language(Path("fr_maths.m4a")) == "fr"
    assert probe.language(Path("Kind IT 3.ogg")) == "it"
    assert probe.language(Path("02-unknown.webm")) == ""


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg on PATH")
def test_ffmpeg_makes_the_wav_the_endpoint_takes(tmp_path: Path) -> None:
    """Converted to a file, not a pipe, so the chunk sizes the length is read from are written."""
    source = tmp_path / "memo.wav"
    source.write_bytes(recordings.wav(2, rate=44_100, channels=1))  # silence, another layout

    recording = voice_audio.read(probe.ffmpeg(source, probe.SendAs.WAV), "audio/wav")

    assert recording.seconds == pytest.approx(2, abs=0.05)
