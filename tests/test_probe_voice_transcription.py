"""#478: the real-recording retest runs each file the way the endpoint would.

`scripts/probe_voice_transcription.py` reads a folder of recordings, checks each
one with the endpoint's own `check_recording`, sends the ones it takes to the
transcriber and reports container, length, time taken and what was heard next
to what was said (`<name>.txt`). These tests run it against the Converse double;
the real run is the operator's, on their SSO session.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fakes import recordings
from fakes.converse import FakeConverse, client_error
from scripts import probe_voice_transcription as probe
from stoa import aws


@pytest.fixture(autouse=True)
def _no_installed_clients():
    yield
    aws.install(None)


def _folder(tmp_path: Path) -> Path:
    folder = tmp_path / "recordings"
    folder.mkdir()
    (folder / "01-kind-gsw-laerm.webm").write_bytes(recordings.webm(6))
    (folder / "01-kind-gsw-laerm.txt").write_text("Wie viel isch drü mal vier?\n", encoding="utf-8")
    (folder / "02-fr.m4a").write_bytes(recordings.mp4(4))
    (folder / "03-voice-memo.wav").write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 64)
    (folder / "04-too-long.ogg").write_bytes(recordings.ogg(75))
    (folder / "notes.md").write_text("not a recording", encoding="utf-8")
    return folder


def test_each_recording_is_checked_timed_and_set_next_to_what_was_said(tmp_path: Path) -> None:
    voxtral = FakeConverse("Wie viel isch drü mal vier?", "Combien font trois fois quatre ?")
    aws.install({aws.Kind.VOICE_TRANSCRIPTION: voxtral})

    rows = probe.run(_folder(tmp_path))

    assert [row.name for row in rows] == [
        "01-kind-gsw-laerm.webm",
        "02-fr.m4a",
        "03-voice-memo.wav",
        "04-too-long.ogg",
    ]
    gsw, fr, wav, too_long = rows
    assert (gsw.language, gsw.container, gsw.outcome, gsw.heard, gsw.said) == (
        "gsw",
        "webm",
        "transcribed",
        "Wie viel isch drü mal vier?",
        "Wie viel isch drü mal vier?",
    )
    assert gsw.seconds == pytest.approx(6, abs=0.6)
    assert gsw.elapsed_ms is not None and gsw.elapsed_ms >= 0
    assert (gsw.sent_as, gsw.word_error) == ("webm", 0)
    assert (fr.language, fr.container, fr.outcome, fr.said, fr.word_error) == (
        "fr",
        "mp4",
        "transcribed",
        "",
        None,
    )
    # Only the two the endpoint would take reach the model, each sent as the endpoint sends it.
    assert [r["messages"][0]["content"][0]["audio"]["format"] for r in voxtral.requests] == [
        "webm",
        "mp4",
    ]
    assert (wav.container, wav.outcome, wav.elapsed_ms) == ("", "voice_recording_unsupported", None)
    assert (too_long.container, too_long.outcome, too_long.elapsed_ms) == (
        "ogg",
        "voice_recording_too_long",
        None,
    )


def test_a_refusal_is_reported_as_the_one_the_alarm_counts(tmp_path: Path) -> None:
    folder = tmp_path / "one"
    folder.mkdir()
    (folder / "a.webm").write_bytes(recordings.webm(3))
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
    (folder / "a.webm").write_bytes(recordings.webm(3))

    table = probe.markdown(probe.run(folder), model_id="mistral.voxtral-small-24b-2507")

    lines = table.splitlines()
    assert "mistral.voxtral-small-24b-2507" in lines[0]
    header = next(i for i, line in enumerate(lines) if line.startswith("| File"))
    assert lines[header + 1].startswith("|---")
    [row] = lines[header + 2 :]
    assert row.startswith("| a.webm |  | webm | 3.")
    # A pipe or line break in what was heard cannot break the table.
    assert "x \\| y zwei" in row


def test_send_as_wav_converts_only_what_the_endpoint_would_take(tmp_path: Path) -> None:
    """Voxtral takes only mp3 and wav (#542): the voice is measured on a converted copy."""
    voxtral = FakeConverse("Wie viel isch drü mal vier?", "Combien font trois fois quatre ?")
    aws.install({aws.Kind.VOICE_TRANSCRIPTION: voxtral})
    converted: list[tuple[str, probe.SendAs]] = []

    def convert(path: Path, send_as: probe.SendAs) -> bytes:
        converted.append((path.name, send_as))
        return b"RIFF-converted-" + path.name.encode()

    rows = probe.run(_folder(tmp_path), send_as=probe.SendAs.WAV, convert=convert)

    assert converted == [("01-kind-gsw-laerm.webm", "wav"), ("02-fr.m4a", "wav")]
    assert [r["messages"][0]["content"][0]["audio"] for r in voxtral.requests] == [
        {"format": "wav", "source": {"bytes": b"RIFF-converted-01-kind-gsw-laerm.webm"}},
        {"format": "wav", "source": {"bytes": b"RIFF-converted-02-fr.m4a"}},
    ]
    gsw, fr, wav, too_long = rows
    # The row keeps what the endpoint received and says what the model was sent.
    assert (gsw.container, gsw.sent_as, gsw.outcome) == ("webm", "wav", "transcribed")
    assert (fr.container, fr.sent_as) == ("mp4", "wav")
    assert (wav.sent_as, too_long.sent_as) == ("", "")


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
