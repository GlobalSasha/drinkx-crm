"""Tests for Sprint 1.3.F — Knowledge Base loader (app/enrichment/kb.py).

All tests use tmp_path and monkeypatch to avoid touching the real KB files.
No real LLM calls.
"""
from __future__ import annotations

import pathlib
import textwrap

import pytest

# We need to monkeypatch _KB_PATH before lru_cache is called, so we do it
# inside each test that needs it, clearing the cache first.


def _write_md(dir_: pathlib.Path, name: str, content: str) -> pathlib.Path:
    p = dir_ / name
    p.write_text(content, encoding="utf-8")
    return p


def _frontmatter(slug: str, title: str, segments: list[str], priority: int = 5, always_on: bool = False) -> str:
    segs = "[" + ", ".join(segments) + "]" if segments else "[]"
    return textwrap.dedent(f"""\
        ---
        slug: {slug}
        title: {title}
        segments: {segs}
        priority: {priority}
        always_on: {"true" if always_on else "false"}
        ---
    """)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_kb_cache():
    """Clear lru_cache before and after each test."""
    from app.enrichment import kb as kb_mod
    kb_mod.load_kb.cache_clear()
    yield
    kb_mod.load_kb.cache_clear()


@pytest.fixture()
def kb_dir(tmp_path):
    """Return a temp directory pre-populated with a small KB."""
    # always_on files
    _write_md(tmp_path, "objections_common.md", _frontmatter("objections_common", "Возражения", [], always_on=True) + "Текст возражений.")
    _write_md(tmp_path, "competitors.md", _frontmatter("competitors", "Конкуренты", [], always_on=True) + "Текст о конкурентах.")
    _write_md(tmp_path, "icp_definition.md", _frontmatter("icp_definition", "ICP Definition", [], always_on=True) + "Текст про ICP.")
    # segment-specific
    _write_md(tmp_path, "playbook_horeca.md", _frontmatter("playbook_horeca", "HoReCa", ["horeca", "coffee_shops"], priority=10) + "Текст плейбука HoReCa.")
    _write_md(tmp_path, "playbook_retail.md", _frontmatter("playbook_retail", "Ритейл", ["food_retail"], priority=10) + "Текст плейбука ритейл.")
    # README — must be skipped
    _write_md(tmp_path, "README.md", "# Just a readme")
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_load_kb_reads_all_files(kb_dir, monkeypatch):
    """load_kb returns entries for every *.md except README."""
    from app.enrichment import kb as kb_mod
    monkeypatch.setattr(kb_mod, "_KB_PATH", kb_dir)
    entries = kb_mod.load_kb()
    slugs = {e.slug for e in entries}
    assert "objections_common" in slugs
    assert "competitors" in slugs
    assert "icp_definition" in slugs
    assert "playbook_horeca" in slugs
    assert "playbook_retail" in slugs
    assert len(entries) == 5


def test_load_kb_skips_readme(kb_dir, monkeypatch):
    """README.md must not appear as a KB entry."""
    from app.enrichment import kb as kb_mod
    monkeypatch.setattr(kb_mod, "_KB_PATH", kb_dir)
    entries = kb_mod.load_kb()
    slugs = [e.slug for e in entries]
    assert "readme" not in slugs
    assert "README" not in slugs


def test_parse_frontmatter_extracts_metadata(tmp_path, monkeypatch):
    """Frontmatter fields are parsed into KBEntry attributes correctly."""
    from app.enrichment import kb as kb_mod
    content = _frontmatter("my_slug", "My Title", ["seg_a", "seg_b"], priority=7, always_on=False) + "Body text here."
    path = tmp_path / "my_slug.md"
    path.write_text(content, encoding="utf-8")
    entry = kb_mod._parse_one(path)
    assert entry is not None
    assert entry.slug == "my_slug"
    assert entry.title == "My Title"
    assert "seg_a" in entry.segments
    assert "seg_b" in entry.segments
    assert entry.priority == 7
    assert entry.always_on is False
    assert "Body text here." in entry.body


def test_parse_handles_missing_frontmatter(tmp_path):
    """File without YAML frontmatter still loads with stem as slug, empty segments."""
    from app.enrichment import kb as kb_mod
    path = tmp_path / "plain_file.md"
    path.write_text("Just some body text without frontmatter.\n", encoding="utf-8")
    entry = kb_mod._parse_one(path)
    assert entry is not None
    assert entry.slug == "plain_file"
    assert entry.segments == ()
    assert entry.priority == 0
    assert entry.always_on is False
    assert "body text" in entry.body


def test_select_for_segment_includes_always_on(kb_dir, monkeypatch):
    """Always-on entries appear regardless of segment."""
    from app.enrichment import kb as kb_mod
    monkeypatch.setattr(kb_mod, "_KB_PATH", kb_dir)
    result = kb_mod.select_for_segment("food_retail")
    slugs = {e.slug for e in result}
    assert "objections_common" in slugs
    assert "competitors" in slugs
    assert "icp_definition" in slugs


def test_select_for_segment_picks_highest_priority_match(tmp_path, monkeypatch):
    """When two playbooks match the segment, the one with higher priority wins."""
    from app.enrichment import kb as kb_mod
    _write_md(tmp_path, "low_prio.md", _frontmatter("low_prio", "Low", ["horeca"], priority=3) + "Low body.")
    _write_md(tmp_path, "high_prio.md", _frontmatter("high_prio", "High", ["horeca"], priority=9) + "High body.")
    monkeypatch.setattr(kb_mod, "_KB_PATH", tmp_path)
    result = kb_mod.select_for_segment("horeca")
    segment_entries = [e for e in result if not e.always_on]
    assert len(segment_entries) == 1
    assert segment_entries[0].slug == "high_prio"


def test_select_for_segment_returns_only_always_on_when_unknown_segment(kb_dir, monkeypatch):
    """Unknown segment → only always_on entries, no segment playbook."""
    from app.enrichment import kb as kb_mod
    monkeypatch.setattr(kb_mod, "_KB_PATH", kb_dir)
    result = kb_mod.select_for_segment("unknown_segment_xyz")
    assert all(e.always_on for e in result)
    # should have 3 always_on entries from kb_dir
    assert len(result) == 3


def test_render_kb_for_prompt_caps_total_chars(tmp_path, monkeypatch):
    """Total output must not exceed _MAX_TOTAL_CHARS."""
    from app.enrichment import kb as kb_mod
    # Write 5 always-on entries each with a 2000-char body (> per-entry cap of 1800)
    for i in range(5):
        body = "X" * 2000
        content = _frontmatter(f"big_{i}", f"Big {i}", [], always_on=True) + body
        _write_md(tmp_path, f"big_{i}.md", content)
    monkeypatch.setattr(kb_mod, "_KB_PATH", tmp_path)
    rendered = kb_mod.render_kb_for_prompt(None)
    assert len(rendered) <= kb_mod._MAX_TOTAL_CHARS


def test_render_kb_for_prompt_returns_empty_when_no_entries(tmp_path, monkeypatch):
    """Empty KB directory → empty string returned."""
    from app.enrichment import kb as kb_mod
    monkeypatch.setattr(kb_mod, "_KB_PATH", tmp_path)
    rendered = kb_mod.render_kb_for_prompt("horeca")
    assert rendered == ""


def test_render_kb_for_prompt_includes_segment_playbook(kb_dir, monkeypatch):
    """Rendered block includes segment-specific playbook title."""
    from app.enrichment import kb as kb_mod
    monkeypatch.setattr(kb_mod, "_KB_PATH", kb_dir)
    rendered = kb_mod.render_kb_for_prompt("horeca")
    assert "HoReCa" in rendered
    assert "Возражения" in rendered  # always_on
