import pytest

from app.activity.files import (
    MAX_FILE_BYTES,
    FileTooLarge,
    UnsupportedFileType,
    classify_upload,
)


def test_classify_pdf():
    kind, content_type = classify_upload(filename="report.pdf", size=1234, content_head=b"%PDF-1.7")
    assert kind == "pdf"
    assert content_type == "application/pdf"


def test_classify_image():
    kind, _ = classify_upload(filename="photo.jpg", size=10, content_head=b"\xff\xd8\xff\xe0")
    assert kind == "image"


def test_classify_xlsx():
    kind, ct = classify_upload(filename="data.xlsx", size=5, content_head=b"PK\x03\x04")
    assert kind == "spreadsheet"
    assert "spreadsheet" in ct or ct == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_classify_audio():
    kind, _ = classify_upload(filename="call.mp3", size=5, content_head=b"ID3\x03")
    assert kind == "audio"


def test_classify_plain_text():
    kind, _ = classify_upload(filename="notes.txt", size=10, content_head=b"hello")
    assert kind == "text"


def test_classify_rejects_executable():
    with pytest.raises(UnsupportedFileType):
        classify_upload(filename="payload.exe", size=10, content_head=b"MZ\x90\x00")


def test_classify_rejects_oversize():
    with pytest.raises(FileTooLarge):
        classify_upload(filename="movie.mp4", size=MAX_FILE_BYTES + 1, content_head=b"")


def test_classify_strips_double_extension_attack():
    """`invoice.pdf.exe` must be rejected — outer extension wins."""
    with pytest.raises(UnsupportedFileType):
        classify_upload(filename="invoice.pdf.exe", size=10, content_head=b"")


def test_classify_rejects_pdf_with_exe_content():
    """A renamed executable (`evil.exe` → `evil.pdf`) must be rejected:
    the PE/exe `MZ` header does not match the PDF signature."""
    with pytest.raises(UnsupportedFileType):
        classify_upload(filename="evil.pdf", size=10, content_head=b"MZ\x90\x00")


def test_classify_pdf_with_valid_signature():
    """A `.pdf` carrying real PDF magic bytes passes."""
    kind, ct = classify_upload(
        filename="invoice.pdf", size=10, content_head=b"%PDF-1.7\x0a%\xe2\xe3\xcf\xd3"
    )
    assert kind == "pdf"
    assert ct == "application/pdf"


def test_classify_txt_skips_signature_check():
    """Text types have no signature; arbitrary bytes pass."""
    kind, _ = classify_upload(filename="notes.txt", size=10, content_head=b"\x00\x01\x02\x03")
    assert kind == "text"


def test_classify_png_with_valid_signature():
    kind, _ = classify_upload(
        filename="logo.png", size=10, content_head=b"\x89PNG\r\n\x1a\n\x00\x00"
    )
    assert kind == "image"


def test_classify_rejects_png_with_gif_content():
    """A `.png` whose bytes are actually a GIF must be rejected."""
    with pytest.raises(UnsupportedFileType):
        classify_upload(filename="fake.png", size=10, content_head=b"GIF89a\x00\x00")
