"""Bounded structural validation for student uploads."""

from __future__ import annotations

from dataclasses import dataclass
import codecs
from io import BytesIO
import posixpath
from pathlib import PurePosixPath
import unicodedata
from urllib.parse import unquote, urlsplit
import warnings
from xml.parsers import expat
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile

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
_OOXML_FACTS = {
    "docx": (
        "word/",
        "word/document.xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    ),
    "pptx": (
        "ppt/",
        "ppt/presentation.xml",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
    ),
    "xlsx": (
        "xl/",
        "xl/workbook.xml",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
    ),
}
_OOXML_ROOTS = {extension: facts[0] for extension, facts in _OOXML_FACTS.items()}
_MAX_ARCHIVE_MEMBERS = 2048
_MAX_ARCHIVE_UNCOMPRESSED = 100 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 100
_MAX_XML_MEMBER_BYTES = 8 * 1024 * 1024
_OFFICE_DOCUMENT_RELATIONSHIP_TYPES = {
    "http://schemas.openxmlformats.org/officedocument/2006/relationships/officedocument",
    "http://purl.oclc.org/ooxml/officedocument/relationships/officedocument",
}
_ACTIVE_MEMBER_MARKERS = (
    "vbaproject",
    "activex/",
    "embeddings/",
    "externallinks/",
    "macrosheets/",
    "oleobjects/",
    "oleobject",
)
_ACTIVE_TYPE_MARKERS = (
    "macroenabled",
    "vba",
    "activex",
    "oleobject",
    "externallink",
    "attachedtemplate",
)


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


class PassivePackageError(Exception):
    """Closed semantic package failure shared by admission and extraction."""

    def __init__(self, category: str):
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class PassivePackageFacts:
    extension: str
    main_part: str
    main_content_type: str
    member_count: int
    uncompressed_bytes: int


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
    try:
        validate_passive_ooxml(stream, extension)
    except PassivePackageError as error:
        if error.category == "content_mismatch":
            _fail(AttachmentErrorCode.UPLOAD_CONTENT_MISMATCH)
        _fail(AttachmentErrorCode.UPLOAD_INVALID)
    stream.seek(0)
    return DetectedFile(MIME_BY_EXTENSION[extension][0], size)


def validate_passive_ooxml(data, extension: str) -> PassivePackageFacts:
    """Prove one passive OPC graph without trusting filename or raw XML spelling."""
    if extension not in _OOXML_FACTS:
        raise PassivePackageError("content_mismatch")
    stream = BytesIO(data) if isinstance(data, bytes) else data
    root, expected_main, expected_content_type = _OOXML_FACTS[extension]
    try:
        stream.seek(0)
        with ZipFile(stream) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > _MAX_ARCHIVE_MEMBERS:
                raise PassivePackageError("document_limit_exceeded")
            canonical: dict[str, str] = {}
            total = 0
            for info in infos:
                name = _canonical_member_name(info.filename)
                identity = name.casefold()
                if identity in canonical:
                    raise PassivePackageError("invalid_document")
                canonical[identity] = name
                if info.flag_bits & 0x1 or info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
                    raise PassivePackageError("invalid_document")
                total += info.file_size
                if total > _MAX_ARCHIVE_UNCOMPRESSED:
                    raise PassivePackageError("document_limit_exceeded")
                if info.file_size and info.file_size / max(1, info.compress_size) > _MAX_COMPRESSION_RATIO:
                    raise PassivePackageError("document_limit_exceeded")

            names = set(canonical.values())
            if "[Content_Types].xml" not in names or "_rels/.rels" not in names:
                raise PassivePackageError("content_mismatch")
            if expected_main not in names:
                raise PassivePackageError("content_mismatch")
            foreign_roots = {"word/", "ppt/", "xl/"} - {root}
            if any(name.startswith(tuple(foreign_roots)) for name in names):
                raise PassivePackageError("content_mismatch")
            if any(marker in name.casefold() for name in names for marker in _ACTIVE_MEMBER_MARKERS):
                raise PassivePackageError("active_content")

            content_types = _safe_xml_elements(
                _read_bounded_member(archive, "[Content_Types].xml")
            )
            overrides = [
                attrs
                for tag, attrs in content_types
                if tag.casefold() == "override"
                and _normalise_part_name(attrs.get("partname", "")) == expected_main
            ]
            if len(overrides) != 1:
                raise PassivePackageError("content_mismatch")
            actual_content_type = overrides[0].get("contenttype", "")
            if any(marker in actual_content_type.casefold() for marker in _ACTIVE_TYPE_MARKERS):
                raise PassivePackageError("active_content")
            if actual_content_type != expected_content_type:
                raise PassivePackageError("content_mismatch")
            for _, attrs in content_types:
                candidate = attrs.get("contenttype", "")
                if any(marker in candidate.casefold() for marker in _ACTIVE_TYPE_MARKERS):
                    raise PassivePackageError("active_content")

            package_relationships = _relationship_elements(
                _read_bounded_member(archive, "_rels/.rels")
            )
            main_relationships = [
                attrs
                for attrs in package_relationships
                if attrs.get("type", "").casefold() in _OFFICE_DOCUMENT_RELATIONSHIP_TYPES
            ]
            if len(main_relationships) != 1:
                raise PassivePackageError("content_mismatch")
            main_target = _normalise_relationship_target(main_relationships[0])
            if main_target != expected_main:
                raise PassivePackageError("content_mismatch")

            for name in names:
                if name.casefold().endswith(".rels"):
                    for attrs in _relationship_elements(_read_bounded_member(archive, name)):
                        _normalise_relationship_target(attrs)

            # Force bounded reads of every member so CRC and decompressor failures close admission.
            for info in infos:
                _drain_member(archive, info.filename)
    except PassivePackageError:
        raise
    except (BadZipFile, OSError, RuntimeError, ValueError, expat.ExpatError):
        raise PassivePackageError("invalid_document") from None
    finally:
        try:
            stream.seek(0)
        except Exception:
            pass
    return PassivePackageFacts(extension, expected_main, expected_content_type, len(infos), total)


def ensure_safe_xml(data: bytes) -> None:
    """Reject declarations and entity expansion through XML parser events."""
    _safe_xml_elements(data)


def _canonical_member_name(raw_name: str) -> str:
    name = unicodedata.normalize("NFC", raw_name)
    path = PurePosixPath(name)
    if (
        not name
        or name != raw_name
        or name.startswith("/")
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in name
        or "\x00" in name
    ):
        raise PassivePackageError("invalid_document")
    return name


def _normalise_part_name(value: str) -> str:
    if not value.startswith("/"):
        return ""
    return _canonical_member_name(unquote(value[1:]))


def _normalise_relationship_target(attrs: dict[str, str]) -> str:
    target_mode = attrs.get("targetmode", "")
    target = unquote(attrs.get("target", ""))
    relationship_type = attrs.get("type", "")
    split = urlsplit(target)
    if (
        target_mode.casefold() == "external"
        or split.scheme
        or split.netloc
        or target.startswith(("/", "\\"))
        or "\\" in target
        or any(marker in relationship_type.casefold() for marker in _ACTIVE_TYPE_MARKERS)
    ):
        raise PassivePackageError("active_content")
    normalised = posixpath.normpath(target)
    if normalised in {"", ".", ".."} or normalised.startswith("../"):
        raise PassivePackageError("invalid_document")
    return _canonical_member_name(normalised)


def _relationship_elements(data: bytes) -> list[dict[str, str]]:
    return [
        attrs
        for tag, attrs in _safe_xml_elements(data)
        if tag.casefold() == "relationship"
    ]


def _safe_xml_elements(data: bytes) -> list[tuple[str, dict[str, str]]]:
    if len(data) > _MAX_XML_MEMBER_BYTES:
        raise PassivePackageError("document_limit_exceeded")
    elements: list[tuple[str, dict[str, str]]] = []
    parser = expat.ParserCreate(namespace_separator="}")

    def reject(*_args) -> None:
        raise PassivePackageError("active_content")

    def start(name: str, attrs: dict[str, str]) -> None:
        local_name = name.rsplit("}", 1)[-1]
        local_attrs = {
            key.rsplit("}", 1)[-1].casefold(): value for key, value in attrs.items()
        }
        elements.append((local_name, local_attrs))

    parser.StartElementHandler = start
    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.UnparsedEntityDeclHandler = reject
    parser.ExternalEntityRefHandler = lambda *_args: reject()
    parser.Parse(data, True)
    return elements


def _read_bounded_member(archive: ZipFile, name: str) -> bytes:
    try:
        info = archive.getinfo(name)
        if info.file_size > _MAX_XML_MEMBER_BYTES:
            raise PassivePackageError("document_limit_exceeded")
        with archive.open(info) as member:
            value = member.read(_MAX_XML_MEMBER_BYTES + 1)
        if len(value) > _MAX_XML_MEMBER_BYTES:
            raise PassivePackageError("document_limit_exceeded")
        return value
    except PassivePackageError:
        raise
    except (BadZipFile, KeyError, OSError, RuntimeError):
        raise PassivePackageError("invalid_document") from None


def _drain_member(archive: ZipFile, name: str) -> None:
    try:
        with archive.open(name) as member:
            while member.read(1024 * 1024):
                pass
    except (BadZipFile, KeyError, OSError, RuntimeError):
        raise PassivePackageError("invalid_document") from None


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
