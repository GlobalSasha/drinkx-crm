"""Async Supabase Storage client — thin httpx wrapper, no SDK dependency.

API reference: https://supabase.com/docs/reference/storage. We only use three
endpoints: upload (POST /object/{bucket}/{key}), sign (POST /object/sign/{bucket}/{key}),
delete (DELETE /object/{bucket}/{key}).
"""
from __future__ import annotations

import logging
from functools import lru_cache

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


class StorageError(RuntimeError):
    """Raised when Supabase Storage returns a non-2xx (except delete-404 which is swallowed)."""


class SupabaseStorageClient:
    def __init__(self, *, base_url: str, bucket: str, service_key: str, timeout_seconds: float = 30.0):
        self._base = base_url.rstrip("/")
        self._bucket = bucket
        self._service_key = service_key
        self._timeout = timeout_seconds

    def _headers(self, extra: dict | None = None) -> dict:
        # Supabase Storage requires BOTH headers when the secret key is the
        # new opaque `sb_secret_...` format (the legacy JWT-style service_role
        # key only needed Authorization). Sending both works for either flavour
        # — verified against the live prod project 2026-05-23.
        h = {
            "apikey": self._service_key,
            "Authorization": f"Bearer {self._service_key}",
        }
        if extra:
            h.update(extra)
        return h

    async def upload(self, *, key: str, content: bytes, content_type: str) -> None:
        """Upload via POST /object/{bucket}/{key} with binary body. Upserts if exists."""
        url = f"{self._base}/storage/v1/object/{self._bucket}/{key}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url,
                content=content,
                headers=self._headers({"Content-Type": content_type, "x-upsert": "true"}),
            )
        if resp.status_code // 100 != 2:
            raise StorageError(f"upload failed [{resp.status_code}]: {resp.text[:200]}")

    async def create_signed_url(self, *, key: str, expires_in: int = 300) -> str:
        """POST /object/sign/{bucket}/{key} → returns an absolute URL valid for `expires_in` seconds."""
        url = f"{self._base}/storage/v1/object/sign/{self._bucket}/{key}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url,
                json={"expiresIn": expires_in},
                headers=self._headers({"Content-Type": "application/json"}),
            )
        if resp.status_code // 100 != 2:
            raise StorageError(f"sign failed [{resp.status_code}]: {resp.text[:200]}")
        body = resp.json()
        signed_path = body.get("signedURL") or body.get("signedUrl") or ""
        if not signed_path:
            raise StorageError(f"sign response missing signedURL: {resp.text[:200]}")
        # Supabase returns a relative path beginning with /object/sign/...; make it absolute.
        if signed_path.startswith("/"):
            # The relative path already includes /object/sign/...; prefix with /storage/v1 if it doesn't include it.
            if signed_path.startswith("/storage/v1"):
                return f"{self._base}{signed_path}"
            if signed_path.startswith("/object"):
                return f"{self._base}/storage/v1{signed_path}"
            return f"{self._base}{signed_path}"
        return signed_path

    async def list_objects(self, *, prefix: str = "", limit: int = 1000) -> list[dict]:
        """POST /object/list/{bucket} — paginated listing. Returns the items array.

        Each item is a dict with at least `name`, `created_at`, `updated_at` (Supabase
        format). We don't paginate beyond `limit` here — the orphan purger reruns
        weekly, so a partial sweep is acceptable.
        """
        url = f"{self._base}/storage/v1/object/list/{self._bucket}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url,
                json={"prefix": prefix, "limit": limit, "offset": 0},
                headers=self._headers({"Content-Type": "application/json"}),
            )
        if resp.status_code // 100 != 2:
            raise StorageError(f"list failed [{resp.status_code}]: {resp.text[:200]}")
        data = resp.json()
        return data if isinstance(data, list) else []

    async def delete(self, *, key: str) -> None:
        """DELETE /object/{bucket}/{key} — best-effort. 404 (already gone) is swallowed."""
        url = f"{self._base}/storage/v1/object/{self._bucket}/{key}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.delete(url, headers=self._headers())
        if resp.status_code == 404:
            # Redact the slug (last segment) — it may contain PII like a counterparty name
            redacted = key.rsplit("/", 1)[0] + "/<redacted>" if "/" in key else "<redacted>"
            log.info("storage.delete: object already gone", extra={"key": redacted})
            return
        if resp.status_code // 100 != 2:
            raise StorageError(f"delete failed [{resp.status_code}]: {resp.text[:200]}")


@lru_cache(maxsize=1)
def get_storage_client() -> SupabaseStorageClient:
    """Singleton storage client constructed from settings."""
    s = get_settings()
    return SupabaseStorageClient(
        base_url=s.supabase_url,
        bucket=s.supabase_storage_bucket,
        service_key=s.supabase_secret_key,
    )
