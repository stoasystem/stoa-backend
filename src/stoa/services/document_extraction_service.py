"""Bounded, passive text extraction for validated conversation documents."""

from __future__ import annotations

from io import BytesIO
import re
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader


MAX_EXTRACTED_CHARACTERS = 200_000
MAX_PDF_PAGES = 100
MAX_PRESENTATION_SLIDES = 200
MAX_WORKBOOK_SHEETS = 50
MAX_WORKBOOK_CELLS = 100_000

_ACTIVE_MEMBER_PARTS = (
    "vbaproject",
    "activex/",
    "embeddings/",
    "externalLinks/",
    "macrosheets/",
    "oleobject",
)
_XML_PROLOG_MARKERS = (b"<!DOCTYPE", b"<!ENTITY")


class DocumentExtractionFailure(Exception):
    """A stable category-only parser failure; source exception text is discarded."""

    def __init__(self, category: str):
        self.category = category
        super().__init__(category)


def extract_attachment_text(data: bytes, media_type: str) -> str:
    if media_type == "application/pdf":
        return extract_pdf_text(data)
    if media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return extract_docx_text(data)
    if media_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
        return extract_pptx_text(data)
    if media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        return extract_xlsx_text(data)
    if media_type in {"text/plain", "text/markdown"}:
        return extract_plain_text(data)
    if media_type in {"image/jpeg", "image/png"}:
        raise DocumentExtractionFailure("no_extractable_text")
    raise DocumentExtractionFailure("unsupported_document")


def extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise DocumentExtractionFailure("encrypted_document")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentExtractionFailure("document_limit_exceeded")
        parts: list[str] = []
        length = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            length = _append_bounded(parts, text, length)
        return "\n".join(parts)
    except DocumentExtractionFailure:
        raise
    except Exception:
        raise DocumentExtractionFailure("invalid_document") from None


def extract_docx_text(data: bytes) -> str:
    try:
        with _passive_archive(data) as archive:
            return _xml_text(archive, "word/document.xml", {"t"})
    except DocumentExtractionFailure:
        raise
    except Exception:
        raise DocumentExtractionFailure("invalid_document") from None


def extract_pptx_text(data: bytes) -> str:
    try:
        with _passive_archive(data) as archive:
            slides = sorted(
                (
                    name
                    for name in archive.namelist()
                    if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
                ),
                key=lambda value: int(re.search(r"(\d+)", value).group(1)),
            )
            if len(slides) > MAX_PRESENTATION_SLIDES:
                raise DocumentExtractionFailure("document_limit_exceeded")
            return _join_bounded(_xml_text(archive, name, {"t"}) for name in slides)
    except DocumentExtractionFailure:
        raise
    except Exception:
        raise DocumentExtractionFailure("invalid_document") from None


def extract_xlsx_text(data: bytes) -> str:
    try:
        with _passive_archive(data) as archive:
            shared = _xml_values(archive, "xl/sharedStrings.xml", {"t"}, required=False)
            sheets = sorted(
                (
                    name
                    for name in archive.namelist()
                    if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
                ),
                key=lambda value: int(re.search(r"(\d+)", value).group(1)),
            )
            if len(sheets) > MAX_WORKBOOK_SHEETS:
                raise DocumentExtractionFailure("document_limit_exceeded")
            output: list[str] = []
            length = 0
            cells = 0
            for sheet in sheets:
                xml = _read_xml_member(archive, sheet)
                cell_type: str | None = None
                formula = False
                for event, element in ElementTree.iterparse(BytesIO(xml), events=("start", "end")):
                    tag = _local_name(element.tag)
                    if event == "start" and tag == "c":
                        cell_type = element.attrib.get("t")
                        formula = False
                    elif event == "end" and tag == "f":
                        formula = True
                    elif event == "end" and tag in {"v", "t"} and element.text and not formula:
                        cells += 1
                        if cells > MAX_WORKBOOK_CELLS:
                            raise DocumentExtractionFailure("document_limit_exceeded")
                        value = element.text
                        if tag == "v" and cell_type == "s":
                            try:
                                value = shared[int(value)]
                            except (ValueError, IndexError):
                                raise DocumentExtractionFailure("invalid_document") from None
                        length = _append_bounded(output, value, length)
                    elif event == "end" and tag == "c":
                        cell_type = None
                        formula = False
                    if event == "end":
                        element.clear()
            return "\n".join(output)
    except DocumentExtractionFailure:
        raise
    except Exception:
        raise DocumentExtractionFailure("invalid_document") from None


def extract_plain_text(data: bytes) -> str:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise DocumentExtractionFailure("invalid_document") from None
    if len(text) > MAX_EXTRACTED_CHARACTERS:
        raise DocumentExtractionFailure("document_limit_exceeded")
    return text


def _passive_archive(data: bytes) -> ZipFile:
    try:
        archive = ZipFile(BytesIO(data))
    except BadZipFile:
        raise DocumentExtractionFailure("invalid_document") from None
    lowered = [name.lower() for name in archive.namelist()]
    if any(part in name for name in lowered for part in _ACTIVE_MEMBER_PARTS):
        archive.close()
        raise DocumentExtractionFailure("active_content")
    for name in archive.namelist():
        if name.endswith(".rels"):
            relationship_xml = archive.read(name).lower()
            if b'targetmode="external"' in relationship_xml:
                archive.close()
                raise DocumentExtractionFailure("active_content")
    return archive


def _xml_text(archive: ZipFile, name: str, accepted_tags: set[str]) -> str:
    return "\n".join(_xml_values(archive, name, accepted_tags))


def _xml_values(
    archive: ZipFile, name: str, accepted_tags: set[str], *, required: bool = True
) -> list[str]:
    if name not in archive.namelist():
        if required:
            raise DocumentExtractionFailure("invalid_document")
        return []
    xml = _read_xml_member(archive, name)
    values: list[str] = []
    length = 0
    try:
        for _, element in ElementTree.iterparse(BytesIO(xml), events=("end",)):
            if _local_name(element.tag) in accepted_tags and element.text:
                length = _append_bounded(values, element.text, length)
            element.clear()
    except ElementTree.ParseError:
        raise DocumentExtractionFailure("invalid_document") from None
    return values


def _read_xml_member(archive: ZipFile, name: str) -> bytes:
    try:
        data = archive.read(name)
    except (KeyError, OSError, RuntimeError):
        raise DocumentExtractionFailure("invalid_document") from None
    upper = data.upper()
    if any(marker in upper for marker in _XML_PROLOG_MARKERS):
        raise DocumentExtractionFailure("active_content")
    return data


def _append_bounded(parts: list[str], value: str, length: int) -> int:
    next_length = length + len(value) + (1 if parts else 0)
    if next_length > MAX_EXTRACTED_CHARACTERS:
        raise DocumentExtractionFailure("document_limit_exceeded")
    parts.append(value)
    return next_length


def _join_bounded(values) -> str:
    parts: list[str] = []
    length = 0
    for value in values:
        if value:
            length = _append_bounded(parts, value, length)
    return "\n".join(parts)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
