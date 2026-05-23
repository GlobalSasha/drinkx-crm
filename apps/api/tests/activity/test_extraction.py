"""Pure tests for content extraction. No DB, no storage — the function
takes bytes in and returns text (or None) out."""

from app.activity.extraction import MAX_EXTRACT_BYTES, extract_content


def test_text_kind_decodes_utf8():
    out = extract_content(file_kind="text", file_name="notes.txt", content=b"hello world")
    assert out == "hello world"


def test_text_kind_replaces_bad_utf8():
    out = extract_content(
        file_kind="text", file_name="notes.txt", content=b"valid \xff\xfe garbage"
    )
    assert out is not None
    assert "valid" in out


def test_empty_content_returns_none():
    assert extract_content(file_kind="text", file_name="empty.txt", content=b"") is None
    assert extract_content(file_kind="pdf", file_name="empty.pdf", content=b"") is None


def test_unsupported_kind_returns_none():
    assert extract_content(file_kind="image", file_name="x.png", content=b"\x89PNG\r\n") is None
    assert extract_content(file_kind="audio", file_name="x.mp3", content=b"ID3") is None
    assert extract_content(file_kind="spreadsheet", file_name="x.xlsx", content=b"PK") is None
    assert extract_content(file_kind="document", file_name="x.docx", content=b"PK") is None


def test_pdf_corrupt_returns_none():
    """Malformed PDF should be caught by the inner try and downgraded to None."""
    out = extract_content(file_kind="pdf", file_name="bad.pdf", content=b"NOT_A_PDF")
    assert out is None


def test_pdf_minimal_does_not_raise():
    """A minimal but valid PDF shell — pypdf should at least parse without
    raising. Empty body → empty extracted text is fine."""
    minimal = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\n"
        b"xref\n0 3\n0000000000 65535 f \n0000000015 00000 n \n0000000057 00000 n \n"
        b"trailer<</Size 3/Root 1 0 R>>\n"
        b"startxref\n98\n%%EOF"
    )
    out = extract_content(file_kind="pdf", file_name="empty.pdf", content=minimal)
    # Either it returns "" (no pages) or None (parser bailed) — both fine.
    assert out is None or isinstance(out, str)


def test_truncation_caps_at_max_bytes():
    """Anything beyond MAX_EXTRACT_BYTES is truncated."""
    big = "x" * (MAX_EXTRACT_BYTES + 1000)
    out = extract_content(file_kind="text", file_name="big.txt", content=big.encode("utf-8"))
    assert out is not None
    assert len(out.encode("utf-8")) <= MAX_EXTRACT_BYTES


def test_truncation_preserves_utf8_boundary():
    """Truncation must not produce invalid utf-8 mid-character."""
    # 4-byte emoji at the boundary — verify decode-with-ignore drops cleanly
    head = "x" * (MAX_EXTRACT_BYTES - 2)
    big = head + "🚀🚀🚀🚀"  # multi-byte chars at the cutoff
    out = extract_content(file_kind="text", file_name="emoji.txt", content=big.encode("utf-8"))
    assert out is not None
    # Should encode cleanly back to valid utf-8
    out.encode("utf-8")  # raises if invalid
