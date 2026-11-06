"""What an uploaded file's bytes must be: `validate_uploaded_file`.

The supported types by their content, not their name; everything else refused
before it is parsed, and a refusal never quotes the bytes it refused. Moved here
from `test_attachment_security.py` (#254).
"""

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from stoa.services.file_validation_service import ValidationFailure, validate_uploaded_file


def _image(fmt: str, size: tuple[int, int] = (8, 8)) -> bytes:
    from PIL import Image

    output = BytesIO()
    Image.new("RGB", size, "white").save(output, format=fmt)
    return output.getvalue()


def _pdf() -> bytes:
    from pypdf import PdfWriter

    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=10, height=10)
    writer.write(output)
    return output.getvalue()


def _ooxml(root: str) -> bytes:
    facts = {
        "word": (
            "word/document.xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        ),
        "ppt": (
            "ppt/presentation.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
        ),
        "xl": (
            "xl/workbook.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
        ),
    }
    main, content_type = facts[root]
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            f'<Types><Override PartName="/{main}" ContentType="{content_type}"/></Types>',
        )
        archive.writestr(
            "_rels/.rels",
            f'<Relationships><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="{main}"/></Relationships>',
        )
        archive.writestr(main, "<root/>")
    return output.getvalue()


@pytest.mark.parametrize(
    "filename,mime,data,canonical",
    [
        ("x.jpg", "image/jpeg", _image("JPEG"), "image/jpeg"),
        ("x.png", "image/png", _image("PNG"), "image/png"),
        ("x.pdf", "application/pdf", _pdf(), "application/pdf"),
        (
            "x.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _ooxml("word"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "x.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            _ooxml("ppt"),
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        (
            "x.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            _ooxml("xl"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ("x.txt", "text/plain", b"safe text", "text/plain"),
        ("x.md", "text/markdown", b"# safe", "text/markdown"),
    ],
    ids=["jpeg", "png", "pdf", "docx", "pptx", "xlsx", "text", "markdown"],
)
def test_validate_supported_bytes(filename: str, mime: str, data: bytes, canonical: str) -> None:
    detected = validate_uploaded_file(data, filename, mime)
    assert detected.media_type == canonical
    assert detected.size_bytes == len(data)


@pytest.mark.parametrize("filename", ["x.gif", "x.webp", "x.heic", "x.doc", "x.ppt", "x.xls"])
def test_validate_rejects_unsupported_before_parsing(filename: str) -> None:
    with pytest.raises(ValidationFailure) as error:
        validate_uploaded_file(b"provider-content-canary", filename, "application/octet-stream")
    assert error.value.code.value == "upload_type_not_supported"
    assert "provider-content-canary" not in str(error.value)


def test_validate_rejects_mime_magic_dimension_archive_and_utf8_failures() -> None:
    cases = [
        (b"not png", "x.png", "image/png", "upload_invalid"),
        (_image("PNG"), "x.png", "image/jpeg", "upload_content_mismatch"),
        (_image("PNG", (4097, 1)), "x.png", "image/png", "upload_invalid"),
        (b"\xff", "x.txt", "text/plain", "upload_invalid"),
        (b"a\x00b", "x.md", "text/plain", "upload_invalid"),
    ]
    for data, filename, mime, code in cases:
        with pytest.raises(ValidationFailure) as error:
            validate_uploaded_file(data, filename, mime)
        assert error.value.code.value == code


def test_validate_rejects_ooxml_traversal_and_compression_ratio() -> None:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "x")
        archive.writestr("../secret", "x")
    with pytest.raises(ValidationFailure) as error:
        validate_uploaded_file(output.getvalue(), "x.docx", MIME_BY_EXTENSION_DOCX)
    assert error.value.code.value == "upload_invalid"


MIME_BY_EXTENSION_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
