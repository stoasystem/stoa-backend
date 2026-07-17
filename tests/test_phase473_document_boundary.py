from __future__ import annotations

from io import BytesIO
import hashlib
import struct
import sys
from types import SimpleNamespace
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest
from pypdf import PdfWriter

from stoa.config import Settings
from stoa.security.attachment_errors import AttachmentErrorCode
from stoa.services.attachment_service import (
    AttachmentContextDisposition,
    extract_message_attachment_context,
)
from stoa.services.document_extraction_service import (
    DocumentExtractionFailure,
    extract_attachment_text,
)
from stoa.services.file_validation_service import ValidationFailure, validate_uploaded_file


OOXML = {
    "docx": {
        "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "main": "word/document.xml",
        "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        "body": '<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>safe</w:t></w:r></w:p></w:body></w:document>',
    },
    "pptx": {
        "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "main": "ppt/presentation.xml",
        "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
        "body": '<p:presentation xmlns:p="urn:p"/>',
    },
    "xlsx": {
        "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "main": "xl/workbook.xml",
        "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
        "body": '<workbook xmlns="urn:x"/>',
    },
}


def _content_types(extension: str, *, content_type: str | None = None) -> str:
    facts = OOXML[extension]
    return (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        f'<Override PartName="/{facts["main"]}" '
        f'ContentType="{content_type or facts["content_type"]}"/>'
        '</Types>'
    )


def _package_relationship(
    extension: str,
    *,
    target: str | None = None,
    relationship_type: str = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
    target_mode: str | None = None,
) -> str:
    mode = f' TargetMode="{target_mode}"' if target_mode else ""
    return (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{relationship_type}" '
        f'Target="{target or OOXML[extension]["main"]}"{mode}/>'
        '</Relationships>'
    )


def _opc(
    extension: str,
    *,
    content_types: str | bytes | None = None,
    package_rels: str | bytes | None = None,
    extras: list[tuple[str, str | bytes, int]] | None = None,
    include_main: bool = True,
) -> bytes:
    facts = OOXML[extension]
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            content_types if content_types is not None else _content_types(extension),
        )
        archive.writestr(
            "_rels/.rels",
            package_rels if package_rels is not None else _package_relationship(extension),
        )
        if include_main:
            archive.writestr(facts["main"], facts["body"])
        for name, value, compression in extras or []:
            archive.writestr(name, value, compress_type=compression)
    return output.getvalue()


def _assert_admission_rejected(data: bytes, extension: str, expected: str = "upload_invalid") -> None:
    with pytest.raises(ValidationFailure) as captured:
        validate_uploaded_file(data, f"student.{extension}", OOXML[extension]["mime"])
    assert captured.value.code.value == expected
    assert "student" not in str(captured.value)


@pytest.mark.parametrize("extension", ["docx", "pptx", "xlsx"])
def test_ooxml_admission_proves_expected_semantic_package(extension: str) -> None:
    detected = validate_uploaded_file(
        _opc(extension), f"student.{extension}", OOXML[extension]["mime"]
    )
    assert detected.media_type == OOXML[extension]["mime"]


@pytest.mark.parametrize("extension", ["docx", "pptx", "xlsx"])
@pytest.mark.parametrize(
    "mutation",
    ["missing-main", "wrong-main-type", "missing-main-relationship", "multiple-main-relationships"],
)
def test_ooxml_admission_rejects_wrong_or_ambiguous_main_part(
    extension: str, mutation: str
) -> None:
    facts = OOXML[extension]
    content_types: str | None = None
    package_rels: str | None = None
    include_main = mutation != "missing-main"
    if mutation == "wrong-main-type":
        content_types = _content_types(extension, content_type="application/xml")
    elif mutation == "missing-main-relationship":
        package_rels = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    elif mutation == "multiple-main-relationships":
        package_rels = _package_relationship(extension).replace(
            "</Relationships>",
            f'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="{facts["main"]}"/></Relationships>',
        )
    _assert_admission_rejected(
        _opc(
            extension,
            content_types=content_types,
            package_rels=package_rels,
            include_main=include_main,
        ),
        extension,
        "upload_content_mismatch",
    )


@pytest.mark.parametrize(
    "relationship_xml",
    [
        '<Relationships><Relationship TargetMode = "External" Target="https://private.invalid/x" Type="x"/></Relationships>',
        "<Relationships><Relationship TARGETMODE='external' Target='//private.invalid/x' Type='x'/></Relationships>",
        '<r:Relationships xmlns:r="urn:r"><r:Relationship TargetMode="&#69;xternal" Target="file:///private" Type="x"/></r:Relationships>',
        '<?xml version="1.0" encoding="UTF-16"?><Relationships><Relationship TargetMode="External" Target="http://private.invalid" Type="x"/></Relationships>'.encode("utf-16"),
    ],
)
def test_relationship_external_detection_is_encoding_and_spelling_independent(
    relationship_xml: str | bytes,
) -> None:
    _assert_admission_rejected(
        _opc(
            "docx",
            extras=[("word/_rels/document.xml.rels", relationship_xml, ZIP_DEFLATED)],
        ),
        "docx",
    )


@pytest.mark.parametrize(
    "xml",
    [
        '<!DOCTYPE x [<!ENTITY secret "private-canary">]><Relationships/>',
        '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x SYSTEM "file:///private"><Relationships/>'.encode("utf-16"),
        '<!DOCTYPE x [<!ENTITY a "a"><!ENTITY b "&a;&a;&a;&a;"><!ENTITY c "&b;&b;&b;&b;">]><Relationships>&c;</Relationships>',
    ],
)
def test_xml_doctype_and_entity_events_are_rejected_without_content_leak(
    xml: str | bytes,
) -> None:
    _assert_admission_rejected(_opc("docx", package_rels=xml), "docx")


@pytest.mark.parametrize(
    "name",
    [
        "word/vbaProject.bin",
        "word/activeX/activeX1.xml",
        "word/embeddings/oleObject1.bin",
        "xl/externalLinks/externalLink1.xml",
        "xl/macrosheets/sheet1.xml",
        "ppt/oleObjects/oleObject1.bin",
    ],
)
def test_ooxml_active_parts_are_rejected_case_independently(name: str) -> None:
    extension = "xlsx" if name.startswith("xl/") else "pptx" if name.startswith("ppt/") else "docx"
    _assert_admission_rejected(
        _opc(extension, extras=[(name, b"private-active-canary", ZIP_STORED)]),
        extension,
    )


@pytest.mark.parametrize(
    "extras",
    [
        [("../private.xml", b"x", ZIP_STORED)],
        [("/absolute.xml", b"x", ZIP_STORED)],
        [("word\\document2.xml", b"x", ZIP_STORED)],
        [("WORD/DOCUMENT.XML", b"x", ZIP_STORED)],
        [("word/cafe\u0301.xml", b"x", ZIP_STORED), ("word/caf\u00e9.xml", b"x", ZIP_STORED)],
        [("[content_types].XML", b"x", ZIP_STORED)],
    ],
)
def test_ooxml_member_names_are_canonical_and_collision_free(extras) -> None:
    _assert_admission_rejected(_opc("docx", extras=extras), "docx")


def test_ooxml_hybrid_and_unsupported_compression_are_rejected() -> None:
    _assert_admission_rejected(
        _opc("docx", extras=[("xl/workbook.xml", OOXML["xlsx"]["body"], ZIP_STORED)]),
        "docx",
        "upload_content_mismatch",
    )
    _assert_admission_rejected(
        _opc("docx", extras=[("word/extra.xml", b"x", ZIP_BZIP2)]), "docx"
    )


def _corrupt_first_compressed_member(data: bytes) -> bytes:
    value = bytearray(data)
    local = value.find(b"PK\x03\x04")
    central = value.find(b"PK\x01\x02")
    assert local >= 0 and central >= 0
    local_crc = struct.unpack_from("<I", value, local + 14)[0]
    central_crc = struct.unpack_from("<I", value, central + 16)[0]
    struct.pack_into("<I", value, local + 14, local_crc ^ 0xFFFFFFFF)
    struct.pack_into("<I", value, central + 16, central_crc ^ 0xFFFFFFFF)
    return bytes(value)


def test_ooxml_crc_corruption_has_one_stable_category() -> None:
    _assert_admission_rejected(_corrupt_first_compressed_member(_opc("docx")), "docx")


def test_ooxml_extraction_revalidates_semantics_before_returning_text() -> None:
    hostile = _opc(
        "docx",
        content_types=_content_types(
            "docx", content_type="application/vnd.ms-word.document.macroEnabled.main+xml"
        ),
    )
    with pytest.raises(DocumentExtractionFailure) as captured:
        extract_attachment_text(hostile, OOXML["docx"]["mime"])
    assert captured.value.category == "active_content"


def test_pdf_admission_rejects_encryption_and_malformed_xref() -> None:
    encrypted = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=10, height=10)
    writer.encrypt("secret")
    writer.write(encrypted)
    with pytest.raises(ValidationFailure) as captured:
        validate_uploaded_file(encrypted.getvalue(), "student.pdf", "application/pdf")
    assert captured.value.code is AttachmentErrorCode.UPLOAD_INVALID
    with pytest.raises(ValidationFailure) as captured:
        validate_uploaded_file(b"%PDF-1.7\nprivate malformed xref", "student.pdf", "application/pdf")
    assert captured.value.code is AttachmentErrorCode.UPLOAD_INVALID


class _Body:
    def __init__(self, value: bytes) -> None:
        self.value = value
        self.offset = 0
        self.closed = 0

    def read(self, size: int) -> bytes:
        chunk = self.value[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed += 1


class _ObjectStore:
    def __init__(self, data: bytes, *, etag: str) -> None:
        self.data = data
        self.etag = etag
        self.body: _Body | None = None

    def get_object(self, **_kwargs):
        self.body = _Body(self.data)
        return {"Body": self.body, "ETag": self.etag, "ContentLength": len(self.data)}


def _attachment(data: bytes, *, etag: str = "immutable-etag") -> dict:
    return {
        "attachment_id": "attachment-opaque",
        "owner_id": "student-opaque",
        "status": "active",
        "immutable_object_key": "private-object",
        "immutable_version_id": "private-version",
        "immutable_etag": etag,
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "content_length": len(data),
        "original_filename": "student.docx",
        "detected_type": OOXML["docx"]["mime"],
    }


def test_extraction_reasserts_exact_immutable_etag_and_closes_body() -> None:
    pytest.importorskip("stoa.services.document_parser_worker")
    data = _opc("docx")
    store = _ObjectStore(data, etag="different-etag")
    context = extract_message_attachment_context(
        [("attachment", _attachment(data))],
        s3=store,
        settings=Settings(s3_images_bucket="private"),
    )
    assert context.disposition is AttachmentContextDisposition.RETRYABLE
    assert context.context == ""
    assert context.error_code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert store.body is not None and store.body.closed == 1


def test_parser_worker_is_spawn_safe_and_returns_typed_result() -> None:
    worker = pytest.importorskip("stoa.services.document_parser_worker")

    result = worker.parse_document_isolated(b"bounded text", "text/plain")
    assert result.text == "bounded text"
    assert result.category is None


def test_parser_worker_timeout_terminates_without_raw_diagnostic(monkeypatch) -> None:
    worker = pytest.importorskip("stoa.services.document_parser_worker")

    class Process:
        def __init__(self) -> None:
            self.alive = True
            self.terminated = False
            self.joined = False

        def is_alive(self) -> bool:
            return self.alive

        def terminate(self) -> None:
            self.terminated = True
            self.alive = False

        def join(self, timeout: float) -> None:
            self.joined = True

    class Connection:
        def poll(self, _timeout: float) -> bool:
            return False

        def close(self) -> None:
            pass

    process = Process()
    result = worker._await_worker_result_for_tests(
        process,
        Connection(),
        deadline=0.0,
        monotonic=lambda: 1.0,
    )
    assert result.text is None
    assert result.category == "parser_timeout"
    assert process.terminated and process.joined and not process.is_alive()
    assert "private" not in repr(result)


def test_parser_input_and_decoded_output_limits_are_category_only() -> None:
    worker = pytest.importorskip("stoa.services.document_parser_worker")

    result = worker.parse_document_isolated(
        b"x" * (worker.MAX_PARSER_INPUT_BYTES + 1), "text/plain"
    )
    assert result.text is None
    assert result.category == "document_limit_exceeded"
    assert "x" * 64 not in repr(result)
    decoded = worker.parse_document_isolated(b"x" * 200_001, "text/plain")
    assert decoded.text is None
    assert decoded.category == "document_limit_exceeded"


def test_parser_worker_installs_cpu_memory_and_core_limits_before_parsing(monkeypatch) -> None:
    worker = pytest.importorskip("stoa.services.document_parser_worker")
    calls: list[tuple[int, tuple[int, int]]] = []
    fake = SimpleNamespace(
        RLIMIT_CPU=1,
        RLIMIT_AS=2,
        RLIMIT_CORE=3,
        setrlimit=lambda kind, value: calls.append((kind, value)),
    )
    monkeypatch.setitem(sys.modules, "resource", fake)
    assert worker._apply_resource_limits()
    assert calls == [
        (1, (worker.PARSER_CPU_SECONDS, worker.PARSER_CPU_SECONDS)),
        (2, (worker.PARSER_ADDRESS_SPACE_BYTES, worker.PARSER_ADDRESS_SPACE_BYTES)),
        (3, (0, 0)),
    ]


def test_parser_worker_enforces_pdf_page_and_archive_structure_limits() -> None:
    worker = pytest.importorskip("stoa.services.document_parser_worker")
    pdf = BytesIO()
    writer = PdfWriter()
    for _ in range(101):
        writer.add_blank_page(width=10, height=10)
    writer.write(pdf)
    pdf_result = worker.parse_document_isolated(pdf.getvalue(), "application/pdf")
    assert pdf_result.category == "document_limit_exceeded"

    slides = [
        (f"ppt/slides/slide{index}.xml", "<slide/>", ZIP_DEFLATED)
        for index in range(1, 202)
    ]
    presentation_result = worker.parse_document_isolated(
        _opc("pptx", extras=slides), OOXML["pptx"]["mime"]
    )
    assert presentation_result.category == "document_limit_exceeded"

    sheets = [
        (f"xl/worksheets/sheet{index}.xml", "<worksheet/>", ZIP_DEFLATED)
        for index in range(1, 52)
    ]
    workbook_result = worker.parse_document_isolated(
        _opc("xlsx", extras=sheets), OOXML["xlsx"]["mime"]
    )
    assert workbook_result.category == "document_limit_exceeded"
