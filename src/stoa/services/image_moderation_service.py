"""Machine moderation of uploaded images with Amazon Rekognition (#138).

Every JPEG or PNG is shown to DetectModerationLabels before its upload counts.
Rekognition is not offered in Zurich, so the call goes to the configured EU region
(Frankfurt); only the image is sent and nothing is stored there (ADR-010).

A label refuses the image when its confidence reaches the configured threshold and
its own name, or any of its ancestors in the moderation taxonomy, is a blocked
category. Rekognition reports a lower-level label with its parent's name; the
second level's parents are written down below, so a label returned on its own is
still judged by its top-level category.

No answer is never a pass: when Rekognition cannot be reached, is throttled or
answers with something unreadable, the caller is told moderation is unavailable
and the upload stays unpromoted until a later completion gets an answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
from typing import Any

from botocore.exceptions import ClientError
from PIL import Image

from stoa.config import Settings
from stoa.security.attachment_errors import AttachmentErrorCode
from stoa.services.file_validation_service import ValidationFailure

MODERATED_TYPES = frozenset({"image/jpeg", "image/png"})

# Rekognition's set quotas for an image passed as bytes.
REKOGNITION_MAX_IMAGE_BYTES = 5 * 1000 * 1000
REKOGNITION_MIN_EDGE = 80
REKOGNITION_MAX_EDGE = 10_000
# Long edges tried, largest first, when an image has to be re-encoded to fit.
_RENDITION_LONG_EDGES = (4096, 2048, 1024)
_RENDITION_JPEG_QUALITY = 85

# Errors that say this image cannot be moderated at all. Asking again does not
# help, so the upload is refused as invalid instead of failing as retryable.
_UNREADABLE_IMAGE_ERRORS = frozenset(
    {"ImageTooLargeException", "InvalidImageFormatException", "InvalidParameterException"}
)

# Second-level labels of moderation taxonomy v7 and their top-level category.
_TAXONOMY_PARENTS = {
    "Explicit Nudity": "Explicit",
    "Explicit Sexual Activity": "Explicit",
    "Sex Toys": "Explicit",
    "Non-Explicit Nudity": "Non-Explicit Nudity of Intimate parts and Kissing",
    "Obstructed Intimate Parts": "Non-Explicit Nudity of Intimate parts and Kissing",
    "Kissing on the Lips": "Non-Explicit Nudity of Intimate parts and Kissing",
    "Female Swimwear or Underwear": "Swimwear or Underwear",
    "Male Swimwear or Underwear": "Swimwear or Underwear",
    "Weapons": "Violence",
    "Graphic Violence": "Violence",
    "Death and Emaciation": "Visually Disturbing",
    "Crashes": "Visually Disturbing",
    "Products": "Drugs & Tobacco",
    "Drugs & Tobacco Paraphernalia & Use": "Drugs & Tobacco",
    "Alcohol Use": "Alcohol",
    "Alcoholic Beverages": "Alcohol",
    "Middle Finger": "Rude Gestures",
    "Nazi Party": "Hate Symbols",
    "White Supremacy": "Hate Symbols",
    "Extremist": "Hate Symbols",
}
_MAX_LINEAGE_DEPTH = 5


@dataclass(frozen=True, slots=True)
class ModerationHit:
    """A label that refused an image, and the blocked category it fell under."""

    label: str
    category: str
    confidence: float


class ImageModerationUnavailable(Exception):
    """Moderation gave no answer; the image must not be let through."""

    def __init__(self, cause: str) -> None:
        self.cause = cause
        super().__init__(cause)


class ImageContentBlocked(ValidationFailure):
    """Moderation refused the image. `hits` is what refused it, for review (#139)."""

    def __init__(self, hits: tuple[ModerationHit, ...]) -> None:
        super().__init__(AttachmentErrorCode.UPLOAD_CONTENT_BLOCKED)
        self.hits = hits


def require_image_passes_moderation(
    data: bytes, *, width: int, height: int, client: Any, settings: Settings
) -> None:
    """Return only if moderation answered and found nothing blocked.

    Raises `ImageContentBlocked` on a hit, `ValidationFailure(UPLOAD_INVALID)` when
    Rekognition cannot read the image, and `ImageModerationUnavailable` otherwise.
    """
    if client is None:
        raise ImageModerationUnavailable("no_client")
    shown = _rendition(data, width, height)
    try:
        response = client.detect_moderation_labels(
            Image={"Bytes": shown},
            MinConfidence=float(settings.image_moderation_min_confidence),
        )
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code") or "ClientError")
        if code in _UNREADABLE_IMAGE_ERRORS:
            raise ValidationFailure(AttachmentErrorCode.UPLOAD_INVALID) from None
        raise ImageModerationUnavailable(code) from None
    except Exception as exc:
        raise ImageModerationUnavailable(type(exc).__name__) from None
    hits = _hits(response, settings)
    if hits:
        raise ImageContentBlocked(hits)


def _hits(response: Any, settings: Settings) -> tuple[ModerationHit, ...]:
    labels = response.get("ModerationLabels") if isinstance(response, dict) else None
    if not isinstance(labels, list):
        raise ImageModerationUnavailable("malformed_response")
    parsed: list[tuple[str, str, float]] = []
    for label in labels:
        if not isinstance(label, dict):
            raise ImageModerationUnavailable("malformed_label")
        name = label.get("Name")
        parent = label.get("ParentName") or ""
        confidence = label.get("Confidence")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(parent, str)
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
        ):
            raise ImageModerationUnavailable("malformed_label")
        parsed.append((name, parent, float(confidence)))
    parents = {**_TAXONOMY_PARENTS, **{name: parent for name, parent, _ in parsed if parent}}
    blocked = set(settings.image_moderation_blocked_labels)
    threshold = float(settings.image_moderation_min_confidence)
    hits: list[ModerationHit] = []
    for name, _parent, confidence in parsed:
        if confidence < threshold:
            continue
        category = _blocked_ancestor(name, parents, blocked)
        if category is not None:
            hits.append(ModerationHit(name, category, confidence))
    return tuple(hits)


def _blocked_ancestor(name: str, parents: dict[str, str], blocked: set[str]) -> str | None:
    current: str | None = name
    for _ in range(_MAX_LINEAGE_DEPTH):
        if current is None:
            return None
        if current in blocked:
            return current
        current = parents.get(current)
    return None


def _rendition(data: bytes, width: int, height: int) -> bytes:
    """The image as Rekognition accepts it: at most 5 MB, every edge at least 80 px.

    Most uploads already are, and are sent as they are. A larger one is re-encoded
    smaller, and a thin one (a formula cropped from a screenshot) is enlarged; only
    this copy is sent, the upload itself is stored unchanged.
    """
    if len(data) <= REKOGNITION_MAX_IMAGE_BYTES and min(width, height) >= REKOGNITION_MIN_EDGE:
        return data
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            flat = _flatten(image)
        for long_edge in _RENDITION_LONG_EDGES:
            size = _rendition_size(width, height, long_edge)
            if max(size) > REKOGNITION_MAX_EDGE:
                continue
            output = BytesIO()
            flat.resize(size, Image.Resampling.LANCZOS).save(
                output, "JPEG", quality=_RENDITION_JPEG_QUALITY
            )
            if output.tell() <= REKOGNITION_MAX_IMAGE_BYTES:
                return output.getvalue()
    except Exception:
        pass
    raise ValidationFailure(AttachmentErrorCode.UPLOAD_INVALID)


def _rendition_size(width: int, height: int, long_edge: int) -> tuple[int, int]:
    scale = min(1.0, long_edge / max(width, height))
    scale = max(scale, REKOGNITION_MIN_EDGE / min(width, height))
    return (max(REKOGNITION_MIN_EDGE, math.ceil(width * scale)),
            max(REKOGNITION_MIN_EDGE, math.ceil(height * scale)))


def _flatten(image: Image.Image) -> Image.Image:
    """RGB for JPEG; transparency is laid on white, as a viewer would show it."""
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.getchannel("A"))
        return canvas
    return image.convert("RGB")
