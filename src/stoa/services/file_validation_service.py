"""Bounded structural validation for student uploads."""

from __future__ import annotations

from dataclasses import dataclass
import codecs
from io import BytesIO
from pathlib import PurePosixPath
import warnings
from zipfile import BadZipFile, ZipFile

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from stoa.config import DOCUMENT_MAX_BYTES, IMAGE_MAX_BYTES, IMAGE_MAX_EDGE
from stoa.security.attachment_errors import AttachmentErrorCode


MIME_BY_EXTENSION = {
    "jpg": ("image/jpeg",), "jpeg": ("image/jpeg",), "png": ("image/png",),
    "pdf": ("application/pdf",),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",),
    "pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation",),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",),
    "txt": ("text/plain",), "md": ("text/markdown", "text/plain"),
}
_OOXML_ROOTS = {"docx": "word/", "pptx": "ppt/", "xlsx": "xl/"}
_MAX_ARCHIVE_MEMBERS = 2048
_MAX_ARCHIVE_UNCOMPRESSED = 100 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 100


@dataclass(frozen=True, slots=True)
class DetectedFile:
    media_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None


class ValidationFailure(Exception):
    """A category-only failure safe to translate at the API boundary."""

    def __init__(self, code: AttachmentErrorCode):
        self.code = code
        super().__init__(code.value)


def _fail(code: AttachmentErrorCode) -> None:
    raise ValidationFailure(code)


def validate_uploaded_file(data, filename: str, declared_mime: str) -> DetectedFile:
    stream = BytesIO(data) if isinstance(data, bytes) else data
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed = MIME_BY_EXTENSION.get(ext)
    if allowed is None:
        _fail(AttachmentErrorCode.UPLOAD_TYPE_NOT_SUPPORTED)
    if declared_mime not in allowed:
        _fail(AttachmentErrorCode.UPLOAD_CONTENT_MISMATCH)
    limit = IMAGE_MAX_BYTES if ext in {"jpg", "jpeg", "png"} else DOCUMENT_MAX_BYTES
    if size > limit:
        _fail(AttachmentErrorCode.UPLOAD_TOO_LARGE)
    if ext in {"jpg", "jpeg", "png"}:
        return validate_image(stream, ext, size)
    if ext == "pdf":
        return validate_pdf(stream, size)
    if ext in _OOXML_ROOTS:
        return validate_ooxml(stream, ext, size)
    return validate_text(
        stream,
        "text/markdown" if ext == "md" and declared_mime == "text/markdown" else "text/plain",
        size,
    )


def validate_image(stream, extension: str, size: int) -> DetectedFile:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            stream.seek(0)
            with Image.open(stream, formats=("JPEG", "PNG")) as image:
                expected = "JPEG" if extension in {"jpg", "jpeg"} else "PNG"
                if image.format != expected:
                    _fail(AttachmentErrorCode.UPLOAD_CONTENT_MISMATCH)
                width, height = image.size
                image.verify()
        if max(width, height) > IMAGE_MAX_EDGE:
            _fail(AttachmentErrorCode.UPLOAD_INVALID)
    except ValidationFailure:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError, OSError, ValueError):
        _fail(AttachmentErrorCode.UPLOAD_INVALID)
    stream.seek(0)
    return DetectedFile("image/jpeg" if extension in {"jpg", "jpeg"} else "image/png", size, width, height)


def validate_pdf(stream, size: int) -> DetectedFile:
    stream.seek(0)
    if stream.read(5) != b"%PDF-":
        _fail(AttachmentErrorCode.UPLOAD_CONTENT_MISMATCH)
    try:
        stream.seek(0)
        reader = PdfReader(stream, strict=True)
        if reader.is_encrypted or len(reader.pages) > 500:
            _fail(AttachmentErrorCode.UPLOAD_INVALID)
        for page in reader.pages:
            _ = page.mediabox
    except ValidationFailure:
        raise
    except Exception:
        _fail(AttachmentErrorCode.UPLOAD_INVALID)
    stream.seek(0)
    return DetectedFile("application/pdf", size)


def validate_ooxml(stream, extension: str, size: int) -> DetectedFile:
    root = _OOXML_ROOTS[extension]
    try:
        stream.seek(0)
        with ZipFile(stream) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            if len(infos) > _MAX_ARCHIVE_MEMBERS or "[Content_Types].xml" not in names:
                _fail(AttachmentErrorCode.UPLOAD_INVALID)
            if not any(name.startswith(root) and not name.endswith("/") for name in names):
                _fail(AttachmentErrorCode.UPLOAD_CONTENT_MISMATCH)
            total = 0
            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in info.filename or info.flag_bits & 0x1:
                    _fail(AttachmentErrorCode.UPLOAD_INVALID)
                total += info.file_size
                if total > _MAX_ARCHIVE_UNCOMPRESSED:
                    _fail(AttachmentErrorCode.UPLOAD_INVALID)
                if info.file_size and info.file_size / max(1, info.compress_size) > _MAX_COMPRESSION_RATIO:
                    _fail(AttachmentErrorCode.UPLOAD_INVALID)
                with archive.open(info) as member:
                    while member.read(1024 * 1024):
                        pass
    except ValidationFailure:
        raise
    except (BadZipFile, OSError, RuntimeError, ValueError):
        _fail(AttachmentErrorCode.UPLOAD_INVALID)
    stream.seek(0)
    return DetectedFile(MIME_BY_EXTENSION[extension][0], size)


def validate_text(stream, media_type: str = "text/plain", size: int = 0) -> DetectedFile:
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    controls = characters = 0
    try:
        stream.seek(0)
        while chunk := stream.read(1024 * 1024):
            text = decoder.decode(chunk)
            characters += len(text)
            if "\x00" in text:
                _fail(AttachmentErrorCode.UPLOAD_INVALID)
            controls += sum(ord(char) < 32 and char not in "\n\r\t" for char in text)
        tail = decoder.decode(b"", final=True)
        characters += len(tail)
        controls += sum(ord(char) < 32 and char not in "\n\r\t" for char in tail)
    except UnicodeDecodeError:
        _fail(AttachmentErrorCode.UPLOAD_INVALID)
    if controls > max(2, characters // 100):
        _fail(AttachmentErrorCode.UPLOAD_INVALID)
    stream.seek(0)
    return DetectedFile(media_type, size)
