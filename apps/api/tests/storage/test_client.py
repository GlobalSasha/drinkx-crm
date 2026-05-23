"""Httpx-mocked tests for SupabaseStorageClient. The client is a thin REST wrapper;
no network IO in tests."""
import pytest
import respx
from httpx import Response

from app.storage.client import SupabaseStorageClient, StorageError


@pytest.mark.asyncio
@respx.mock
async def test_upload_object_posts_to_storage_with_service_key():
    route = respx.post(
        "https://example.supabase.co/storage/v1/object/lead-files/ws/lead/act/file.pdf"
    ).mock(return_value=Response(200, json={"Key": "lead-files/ws/lead/act/file.pdf"}))
    c = SupabaseStorageClient(
        base_url="https://example.supabase.co",
        bucket="lead-files",
        service_key="srv-key",
    )
    await c.upload(key="ws/lead/act/file.pdf", content=b"PDF", content_type="application/pdf")
    assert route.called
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer srv-key"
    assert req.headers["Content-Type"] == "application/pdf"
    assert req.content == b"PDF"


@pytest.mark.asyncio
@respx.mock
async def test_upload_raises_storage_error_on_4xx():
    respx.post(
        "https://example.supabase.co/storage/v1/object/lead-files/ws/lead/act/x.pdf"
    ).mock(return_value=Response(409, json={"error": "Duplicate"}))
    c = SupabaseStorageClient(
        base_url="https://example.supabase.co",
        bucket="lead-files",
        service_key="k",
    )
    with pytest.raises(StorageError, match="409"):
        await c.upload(key="ws/lead/act/x.pdf", content=b"x", content_type="application/pdf")


@pytest.mark.asyncio
@respx.mock
async def test_create_signed_url_returns_full_url():
    route = respx.post(
        "https://example.supabase.co/storage/v1/object/sign/lead-files/ws/lead/act/file.pdf"
    ).mock(return_value=Response(200, json={"signedURL": "/object/sign/lead-files/ws/lead/act/file.pdf?token=abc"}))
    c = SupabaseStorageClient(
        base_url="https://example.supabase.co",
        bucket="lead-files",
        service_key="k",
    )
    url = await c.create_signed_url(key="ws/lead/act/file.pdf", expires_in=300)
    assert route.called
    body = route.calls.last.request.read()
    assert b'"expiresIn":300' in body or b'"expiresIn": 300' in body
    assert url == "https://example.supabase.co/storage/v1/object/sign/lead-files/ws/lead/act/file.pdf?token=abc"


@pytest.mark.asyncio
@respx.mock
async def test_delete_object_swallows_404():
    """Deletion is best-effort — a 404 (already gone) must not raise."""
    respx.delete(
        "https://example.supabase.co/storage/v1/object/lead-files/missing/file.pdf"
    ).mock(return_value=Response(404, json={"error": "Not found"}))
    c = SupabaseStorageClient(
        base_url="https://example.supabase.co",
        bucket="lead-files",
        service_key="k",
    )
    await c.delete(key="missing/file.pdf")  # must not raise
