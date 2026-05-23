import uuid

from app.storage.paths import build_object_key, slug_filename


def test_slug_filename_removes_unsafe_chars():
    assert slug_filename("Коммерческое предложение!!!  v3.pdf") == "kommercheskoe-predlozhenie-v3.pdf"
    assert slug_filename("../etc/passwd") == "etc-passwd"
    assert slug_filename("файл с пробелами.docx") == "fail-s-probelami.docx"


def test_slug_filename_preserves_extension():
    assert slug_filename("Invoice 2026/05.xlsx") == "invoice-2026-05.xlsx"


def test_slug_filename_handles_empty_or_dotfile():
    assert slug_filename("") == "file"
    assert slug_filename(".hidden") == "hidden"
    assert slug_filename("noext") == "noext"


def test_build_object_key_layout():
    ws = uuid.UUID("00000000-0000-0000-0000-000000000001")
    lead = uuid.UUID("00000000-0000-0000-0000-000000000002")
    act = uuid.UUID("00000000-0000-0000-0000-000000000003")
    key = build_object_key(workspace_id=ws, lead_id=lead, activity_id=act, filename="Invoice v3.pdf")
    assert key == "00000000-0000-0000-0000-000000000001/00000000-0000-0000-0000-000000000002/00000000-0000-0000-0000-000000000003/invoice-v3.pdf"
