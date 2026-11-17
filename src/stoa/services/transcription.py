"""Speech to text for a voice question: one interface, one implementation (#477).

`Transcriber` is the seam: it takes a recording and its container and gives back
what was said, in the language it was said in. Changing the model or who runs it
changes this file and nothing that calls it.

`VoxtralTranscriber` asks Mistral's Voxtral Small on Bedrock, through Converse,
in the one region it is called in (`voice_transcription_region`, Ireland). What
it sends is fixed by ADR-010: the recording as an `audio` block and the
transcription prompt, nothing else - no student, no conversation, no system
prompt naming either. `request()` builds exactly that, and the tests read it.

The recording lives only in this call. It is not logged: a failure is logged by
the provider's error code and request id alone, and the exception raised carries
no text of the provider's, which could quote what it was sent.
"""

from __future__ import annotations

import logging
from typing import Any, Final, Protocol

from botocore.exceptions import BotoCoreError, ClientError

from stoa import aws, config
from stoa.services.voice_audio import Container

logger = logging.getLogger(__name__)

# Without "do not translate" Voxtral answers a French question in English
# (#469, measured 2026-11-16). It must not answer the question either: Voxtral
# Mini did, which is why Small is used.
PROMPT: Final = (
    "Transcribe this recording exactly as it is spoken, in the language it is "
    "spoken in. Do not translate it. Do not answer, explain, summarise or correct "
    "it. Reply with the transcription only."
)
MAX_TOKENS: Final = 1024


class TranscriptionFailed(RuntimeError):
    """The transcriber did not give a transcription; nothing about the recording is in it.

    `refused` is set when the provider turned the request down as invalid (the
    model not taking audio, or not this container) rather than failing to answer:
    the case #478 alarms on.
    """

    def __init__(self, reason: str, *, refused: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.refused = refused


class Transcriber(Protocol):
    def transcribe(self, audio: bytes, container: Container) -> str:
        """What was said, as text in the spoken language. Raises `TranscriptionFailed`."""
        ...


# Bedrock's own refusal of what it was sent, as opposed to a failure to answer.
_REFUSALS: Final = frozenset({"ValidationException"})


def request(audio: bytes, container: Container, *, model_id: str) -> dict[str, Any]:
    """The whole Converse request for one recording: the audio and the prompt, nothing more."""
    return {
        "modelId": model_id,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"audio": {"format": container.value, "source": {"bytes": audio}}},
                    {"text": PROMPT},
                ],
            }
        ],
        "inferenceConfig": {"maxTokens": MAX_TOKENS, "temperature": 0},
    }


def _text(response: Any) -> str:
    try:
        content = response["output"]["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise TranscriptionFailed("response without a message") from exc
    if not isinstance(content, list):
        raise TranscriptionFailed("response without content")
    return "".join(
        block["text"] for block in content if isinstance(block, dict) and isinstance(block.get("text"), str)
    ).strip()


class VoxtralTranscriber:
    """Voxtral Small on Bedrock Converse, in the voice transcription region."""

    def __init__(self, *, model_id: str | None = None) -> None:
        self.model_id = model_id or config.settings().voice_transcription_model_id

    def transcribe(self, audio: bytes, container: Container) -> str:
        client = aws.client(aws.Kind.VOICE_TRANSCRIPTION)
        try:
            response = client.converse(**request(audio, container, model_id=self.model_id))
        except ClientError as exc:
            error = exc.response.get("Error", {}) if isinstance(exc.response, dict) else {}
            code = str(error.get("Code") or "unknown")
            metadata = exc.response.get("ResponseMetadata", {}) if isinstance(exc.response, dict) else {}
            refused = code in _REFUSALS
            logger.warning(
                "voice transcription %s",
                "refused" if refused else "failed",
                extra={
                    "event": "voice_transcription_refused" if refused else "voice_transcription_failed",
                    "provider_error_code": code,
                    "provider_request_id": str(metadata.get("RequestId") or ""),
                    "model_id": self.model_id,
                    "audio_format": container.value,
                },
            )
            raise TranscriptionFailed(code, refused=refused) from None
        except BotoCoreError as exc:
            logger.warning(
                "voice transcription failed",
                extra={
                    "event": "voice_transcription_failed",
                    "provider_error_code": type(exc).__name__,
                    "model_id": self.model_id,
                    "audio_format": container.value,
                },
            )
            raise TranscriptionFailed(type(exc).__name__) from None
        return _text(response)
