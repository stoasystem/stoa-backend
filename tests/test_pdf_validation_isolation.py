"""PDF structure checks run in the restricted parser process, not the API (#6, E9).

Upload validation handed the whole document to `PdfReader` inside the API
process, which has no CPU or memory limit of its own: a crafted object header
kept pypdf busy until the Lambda died. The structure check now runs in the same
spawn-isolated, rlimited worker that text extraction already uses. The API
keeps only the `%PDF-` magic check, and anything but a clean answer from the
worker - a rejection, a timeout, a killed process - leaves the upload invalid.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter

from stoa.security.attachment_errors import AttachmentErrorCode
from stoa.services import document_parser_worker, file_validation_service
from stoa.services.file_validation_service import ValidationFailure, validate_uploaded_file


def _pdf(pages: int = 1, *, password: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    if password is not None:
        writer.encrypt(password)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def _long_object_header(header_length: int = 4 * 1024 * 1024) -> bytes:
    """The audit's synthetic input: one object number millions of digits long."""
    header = b"%PDF-1.7\n"
    obj = b"9" * header_length + b" 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    pages = b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
    offset = len(header) + len(obj) + len(pages)
    xref = (
        f"xref\n0 3\n0000000000 65535 f \n{len(header):010d} 00000 n \n"
        f"{len(header) + len(obj):010d} 00000 n \n"
        f"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n{offset}\n%%EOF\n"
    ).encode()
    return header + obj + pages + xref


def _rejected(data: bytes) -> AttachmentErrorCode:
    with pytest.raises(ValidationFailure) as failure:
        validate_uploaded_file(data, "student.pdf", "application/pdf")
    return failure.value.code


def test_a_normal_pdf_is_admitted() -> None:
    detected = validate_uploaded_file(_pdf(), "student.pdf", "application/pdf")
    assert detected.media_type == "application/pdf"


def test_an_encrypted_pdf_is_still_refused() -> None:
    assert _rejected(_pdf(password="secret")) is AttachmentErrorCode.UPLOAD_INVALID


def test_a_pdf_over_five_hundred_pages_is_still_refused() -> None:
    assert _rejected(_pdf(pages=501)) is AttachmentErrorCode.UPLOAD_INVALID


def test_a_pdf_of_exactly_five_hundred_pages_is_admitted() -> None:
    detected = validate_uploaded_file(_pdf(pages=500), "student.pdf", "application/pdf")
    assert detected.media_type == "application/pdf"


def test_a_malformed_long_object_header_is_invalid_not_an_error() -> None:
    assert _rejected(_long_object_header()) is AttachmentErrorCode.UPLOAD_INVALID


def test_a_file_that_is_not_a_pdf_is_a_content_mismatch_without_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        file_validation_service.document_parser_worker,
        "validate_pdf_isolated",
        lambda *args, **kwargs: calls.append(args),
    )
    assert _rejected(b"not a pdf at all") is AttachmentErrorCode.UPLOAD_CONTENT_MISMATCH
    assert calls == []


def test_a_check_that_runs_out_of_time_does_not_admit_the_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_validation_service, "PDF_VALIDATION_WALL_SECONDS", 0.0001)
    assert _rejected(_pdf()) is AttachmentErrorCode.UPLOAD_INVALID


@pytest.mark.parametrize(
    "category",
    ["parser_timeout", "service_unavailable", "invalid_document", "encrypted_document",
     "document_limit_exceeded"],
)
def test_every_answer_but_a_clean_one_leaves_the_upload_invalid(
    monkeypatch: pytest.MonkeyPatch, category: str
) -> None:
    monkeypatch.setattr(
        file_validation_service.document_parser_worker,
        "validate_pdf_isolated",
        lambda *_args, **_kwargs: document_parser_worker.ParserResult(category=category),
    )
    assert _rejected(_pdf()) is AttachmentErrorCode.UPLOAD_INVALID


def test_the_api_process_does_not_parse_the_pdf_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    """pypdf in this process refuses everything; the spawned worker has its own."""
    import pypdf

    class _Refuse:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("PdfReader was constructed in the API process")

    from stoa.services import document_extraction_service

    # Every copy this process holds: pypdf's own, and the one the extraction
    # module bound at import, which a direct call to its check would use.
    monkeypatch.setattr(pypdf, "PdfReader", _Refuse)
    monkeypatch.setattr(document_extraction_service, "PdfReader", _Refuse)

    detected = validate_uploaded_file(_pdf(), "student.pdf", "application/pdf")

    assert detected.media_type == "application/pdf"


def test_the_worker_reports_a_clean_structure_check_as_empty_text() -> None:
    result = document_parser_worker.validate_pdf_isolated(_pdf())
    assert result == document_parser_worker.ParserResult(text="")
