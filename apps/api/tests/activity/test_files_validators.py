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
