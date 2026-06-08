"""Unit tests for app.logs.service — the agent-facing log reader."""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from app.logs import service as svc


def test_parse_since_units():
    assert svc._parse_since("30m") == timedelta(minutes=30)
    assert svc._parse_since("2h") == timedelta(hours=2)
    assert svc._parse_since("1d") == timedelta(days=1)
    assert svc._parse_since("90s") == timedelta(seconds=90)
    assert svc._parse_since("nonsense") is None
    assert svc._parse_since("") is None


def test_read_logs_disabled_without_log_dir(monkeypatch):
    monkeypatch.setattr(svc, "get_settings", lambda: SimpleNamespace(log_dir=""))
    res = svc.read_logs()
    assert res["enabled"] is False
    assert res["lines"] == []


def test_read_logs_filters_by_level_and_tags_service(tmp_path, monkeypatch):
    (tmp_path / "app-api.log").write_text(
        '{"level":"info","event":"hi"}\n'
        '{"level":"error","event":"boom"}\n'
        'not-json-but-still-a-line\n',
        encoding="utf-8",
    )
    (tmp_path / "app-worker.log").write_text(
        '{"level":"warning","event":"slow task"}\n', encoding="utf-8"
    )
    monkeypatch.setattr(svc, "get_settings", lambda: SimpleNamespace(log_dir=str(tmp_path)))

    # since="" → skip the time filter (lines have no timestamp)
    errors = svc.read_logs(level="error", since="")
    assert errors["enabled"] is True
    assert errors["count"] == 1
    assert errors["lines"][0]["event"] == "boom"
    assert errors["lines"][0]["service"] == "api"

    # warning level includes the worker warning; service tag comes from filename
    warns = svc.read_logs(level="warning", since="")
    events = {(line["service"], line["event"]) for line in warns["lines"]}
    assert ("worker", "slow task") in events
    assert ("api", "boom") in events  # error >= warning

    # service filter narrows to one file
    only_worker = svc.read_logs(level="all", since="", service="worker")
    assert {line["service"] for line in only_worker["lines"]} == {"worker"}


def test_read_logs_contains_filter(tmp_path, monkeypatch):
    (tmp_path / "app-api.log").write_text(
        '{"level":"error","event":"db timeout"}\n'
        '{"level":"error","event":"validation failed"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(svc, "get_settings", lambda: SimpleNamespace(log_dir=str(tmp_path)))
    res = svc.read_logs(level="error", since="", contains="timeout")
    assert res["count"] == 1
    assert res["lines"][0]["event"] == "db timeout"
