"""Smoke test: orchestrator imports cleanly and helper utilities are pure-callable.
The real flow is exercised by Task 16 (e2e on Postgres)."""
from types import SimpleNamespace

from app.base_update import orchestrator as orch


def test_load_staged_files_filters_garbage():
    job = SimpleNamespace(stats_json={"_staged_files": [
        {"filename": "a.md", "text": "..."},
        {"filename": "", "text": "x"},           # filename empty → dropped
        {"filename": "c.md", "text": ""},        # text empty → dropped
        "not a dict",                            # garbage → dropped
        {"filename": "d.md", "text": "ok"},
    ]})
    files = orch._load_staged_files(job)
    assert [f["filename"] for f in files] == ["a.md", "d.md"]


def test_load_staged_files_empty_stats():
    assert orch._load_staged_files(SimpleNamespace(stats_json=None)) == []
    assert orch._load_staged_files(SimpleNamespace(stats_json={})) == []


def test_clear_staged_files_pops_key_and_keeps_others():
    job = SimpleNamespace(stats_json={"_staged_files": [{"filename": "a.md", "text": "x"}], "keep_me": 1})
    orch._clear_staged_files(job)
    assert job.stats_json == {"keep_me": 1}


def test_clear_staged_files_to_none_when_empty():
    job = SimpleNamespace(stats_json={"_staged_files": []})
    orch._clear_staged_files(job)
    assert job.stats_json is None
