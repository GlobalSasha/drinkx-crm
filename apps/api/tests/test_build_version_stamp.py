"""The deploy release gate reads the build stamp back over HTTP (audit G1).

`.github/workflows/deploy.yml` compares the `sha` field of GET /health against
the commit it just shipped, and fails the release when they differ. Dropping
that field would silently turn the version check back into a plain HTTP 200
check, which the previous release passes just as well.
"""
from fastapi.testclient import TestClient

from app.main import create_app


def _client(monkeypatch, sha: str | None) -> TestClient:
    # The stamp is read when the app is built, so setting the environment
    # before create_app() is enough — no module reload, which would leak into
    # other tests sharing the session.
    if sha is None:
        monkeypatch.delenv("DRINKX_GIT_SHA", raising=False)
    else:
        monkeypatch.setenv("DRINKX_GIT_SHA", sha)
    return TestClient(create_app())


def test_health_reports_the_build_stamp(monkeypatch):
    client = _client(monkeypatch, "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c")
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["sha"] == "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"


def test_version_reports_the_build_stamp(monkeypatch):
    client = _client(monkeypatch, "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c")
    body = client.get("/version").json()
    assert body["sha"] == "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"


def test_unstamped_image_reports_unknown_rather_than_omitting_the_field(monkeypatch):
    # An image built without the GIT_SHA build arg must still answer with a
    # value the gate can compare — and "unknown" never equals a real commit,
    # so such a build can never pass the release check.
    client = _client(monkeypatch, None)
    assert client.get("/health").json()["sha"] == "unknown"
