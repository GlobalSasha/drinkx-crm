#!/usr/bin/env python3
"""Oracle tests for REL-LOCAL-01 (P2-3): safe re-preparation of the same SHA.

`infra/production/remote_prepare_release.sh` currently publishes a release by
doing `rm -rf "$TARGET"` followed by `mv "$STAGING" "$TARGET"` (see the
"--- publish ---" section of that script). When the SHA being (re)prepared is
the one `current` already points at -- the normal case when a successful
deploy of that SHA gets re-run, e.g. a retried CI job -- there is a window
between the `rm -rf` and the `mv` where `current` resolves to nothing. A
crash in that window (killed process, disk full, `mv` failing) leaves
`current` dangling forever, and any reader racing the flip (health checks,
another deploy step, an operator) can observe a missing directory.

These are ORACLE tests written from the frozen task contract
(REL-LOCAL-01_TASK_CONTRACT.md) *before* the fix lands. They encode the
acceptance freeze (REL-SAME-01..04) verbatim. REL-SAME-01 is EXPECTED TO FAIL
on the current code -- that is the contrpример the contract asks for. Do not
adjust these tests to make them pass; only the implementation should change.

Everything runs in a tmpdir sandbox: throwaway git repos, throwaway
DEPLOY_ROOT directories, no SSH, no Docker, no production host, no database.

Run standalone (matches the convention of every other file in this directory,
see infra/production/RELEASE_GATE.md "Regression tests"):

    python3 infra/production/tests/test_release_same_sha_reprepare.py

Also collectible by pytest (each check is wrapped as a test_* function that
asserts no problems were reported):

    python -m pytest infra/production/tests/test_release_same_sha_reprepare.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[2]
PREPARE = REPO_ROOT / "infra" / "production" / "remote_prepare_release.sh"

# --- reuse the existing test suite's fixtures instead of duplicating them --
# test_release_build_context.py is a plain script (no package, no
# conftest.py), so it is loaded by file path and reused as a module. This
# gives us make_repo/make_server/archive/prepare/unlock for free, matching
# how the existing suite already produces valid archives and a valid
# DEPLOY_ROOT.
_spec = importlib.util.spec_from_file_location(
    "test_release_build_context", TESTS_DIR / "test_release_build_context.py"
)
base = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(base)

make_repo = base.make_repo
make_server = base.make_server
archive = base.archive
prepare = base.prepare
unlock = base.unlock

FAKE_SHA_X = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
FAKE_SHA_ROLLBACK = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
MARKER_NAME = "RELEASE_MARKER.txt"


# --- helpers specific to this file -----------------------------------------

def _minimal_tree(marker_body: str) -> dict[str, str]:
    """The files remote_prepare_release.sh requires to accept a release,
    plus a marker file whose content lets a test tell two builds apart."""
    return {
        "infra/production/docker-compose.yml": "name: drinkx\n",
        "infra/production/deploy.sh": "#!/usr/bin/env bash\n",
        "apps/api/Dockerfile": "FROM scratch\n",
        "apps/web/Dockerfile": "FROM scratch\n",
        MARKER_NAME: marker_body,
    }


def build_raw_archive(root: Path, sha: str, files: dict[str, str], *, valid_checksum: bool = True) -> Path:
    """Build incoming/<sha>.tar.gz (+ .sha256) directly with tarfile, bypassing
    git and make_release_archive.sh entirely.

    Needed here because a real git commit's tree is fixed -- it cannot give
    us two different archive bodies for the same SHA -- but "the same SHA
    re-shipped with different/corrupted bytes" is exactly the scenario
    REL-SAME-02 and REL-SAME-03 need, and exactly what the checksum gate
    exists to catch.
    """
    incoming = root / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    archive_path = incoming / f"{sha}.tar.gz"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel, body in files.items():
            data = body.encode()
            info = tarfile.TarInfo(name=rel)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    body_bytes = buf.getvalue()
    archive_path.write_bytes(body_bytes)
    digest = hashlib.sha256(body_bytes).hexdigest()
    if not valid_checksum:
        digest = "0" * 64  # syntactically fine, guaranteed not to match
    (root / "incoming" / f"{sha}.tar.gz.sha256").write_text(digest + "\n")
    return archive_path


def prepare_raw(root: Path, sha: str, extra_path: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, DEPLOY_ROOT=str(root))
    if extra_path:
        env["PATH"] = extra_path + os.pathsep + env["PATH"]
    return subprocess.run(
        ["bash", str(PREPARE), sha],
        env=env, capture_output=True, text=True, timeout=120,
    )


def set_current(root: Path, sha: str) -> None:
    """Mirror what deploy.sh does after a successful prepare+verify: flip the
    `current` symlink onto releases/<sha>. remote_prepare_release.sh itself
    never touches `current` -- deploy.sh owns the flip (rm -f + ln -s) -- so
    tests that need a realistic "current already points here" precondition
    must set it up themselves."""
    current = root / "current"
    target = root / "releases" / sha
    if current.is_symlink() or current.exists():
        current.unlink()
    current.symlink_to(target)


def make_delay_rm_stub(tmp: Path, delay_s: float = 0.3) -> Path:
    """A PATH directory whose `rm` really removes, then sleeps.

    remote_prepare_release.sh's publish step is:

        rm -rf "$TARGET"
        mv "$STAGING" "$TARGET"

    On a fast local filesystem this window is sub-millisecond, too small for
    an external poller to reliably land in. Widening it with a slow `rm` does
    not change the correctness question (an atomic rename-based fix removes
    the `rm -rf` from this path entirely) -- it only makes the existing race
    observable in a test without relying on CPU-scheduling luck. This mirrors
    the approach the task contract itself suggests for REL-SAME-01.
    """
    stub_dir = tmp / "slow-rm-bin"
    stub_dir.mkdir(parents=True, exist_ok=True)
    real_rm = shutil.which("rm") or "/bin/rm"
    script = stub_dir / "rm"
    script.write_text(
        "#!/usr/bin/env bash\n"
        f"{real_rm} \"$@\"\n"
        f"sleep {delay_s}\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return stub_dir


# --- REL-SAME-01 -------------------------------------------------------------

def check_reprepare_never_dangles_current(tmp: Path) -> list[str]:
    """Reprepare the SHA `current` already points at: a concurrent reader
    polling `current` every ~8ms must never see it unresolved or missing its
    tree, for the entire duration of the reprepare."""
    problems: list[str] = []
    repo = tmp / "repo"
    root = tmp / "server"
    sha, _ = make_repo(repo)
    make_server(root)

    archive(repo, root, sha)
    proc = prepare(root, sha)
    if proc.returncode != 0:
        return [f"initial prepare of {sha} failed:\n{proc.stdout}{proc.stderr}"]
    set_current(root, sha)

    # Re-ship the identical commit's archive (the realistic "retried deploy
    # of the same SHA" case) so the reprepare hits the "$TARGET exists"
    # branch that does rm-rf-then-mv.
    archive(repo, root, sha)

    slow_rm_dir = make_delay_rm_stub(tmp)
    current_path = root / "current"

    misses: list[str] = []
    stop = threading.Event()

    def poll_loop() -> None:
        while not stop.is_set():
            resolved = Path(os.path.realpath(current_path))
            is_ok = resolved.is_dir() and (resolved / "infra" / "production" / "docker-compose.yml").is_file()
            if not is_ok:
                misses.append(str(resolved))
            time.sleep(0.008)

    poller = threading.Thread(target=poll_loop, daemon=True)
    poller.start()
    proc2 = prepare_raw(root, sha, extra_path=str(slow_rm_dir))
    stop.set()
    poller.join(timeout=5)

    if proc2.returncode != 0:
        problems.append(f"reprepare of the same SHA failed unexpectedly:\n{proc2.stdout}{proc2.stderr}")

    final_resolved = Path(os.path.realpath(current_path))
    if not final_resolved.is_dir():
        problems.append("current does not resolve to a directory after reprepare finished")

    if misses:
        problems.append(
            f"current was unresolved/incomplete {len(misses)} time(s) out of the polling window "
            f"while reprepare ran (contract REL-SAME-01 requires 0 misses); first miss saw: {misses[0]}"
        )

    unlock(root)
    return problems


# --- REL-SAME-02 -------------------------------------------------------------
#
# On the candidate (053caec) the "reprepare the same SHA" case is no longer a
# single always-replace path. Publish now has three branches, and REL-SAME-02
# is split into one check per branch, per the coordinator's follow-up:
#
#   1. releases/.markers/<sha> matches the incoming archive's sha256 -> the
#      directory is reused untouched (stdout says "reusing").
#   2. no marker (or it doesn't match) but `diff -r -q` says the tree already
#      on disk is byte-identical to what was just unpacked -> also reused,
#      and the marker is (re)written so the fast path applies next time.
#   3. the tree differs from what was unpacked AND `current` points at it ->
#      die with a non-zero exit, the existing directory is left completely
#      alone, and `current` keeps resolving to it.
#
# The original REL-SAME-02 wording ("broken checksum -> fail; corrected
# checksum -> succeeds and replaces the content") assumed the old
# unconditional rm-rf/mv publish. Under the fixed contract, "corrected
# checksum" + "different content" + "current -> TARGET" is exactly branch 3:
# a valid, verified archive must still be REFUSED because replacing the
# release that is serving traffic is the hazard REL-LOCAL-01 exists to
# prevent, not something a passing checksum should override. That scenario
# was moved into check_diverged_content_current_target_refuses below rather
# than kept as a "then it succeeds" assertion, which would now be wrong.
#
# The pre-checksum rejection itself (corrupted bytes -- "checksum" is a
# distinct gate that runs before the publish-branch logic) is unaffected by
# the candidate and is kept as its own check.

def check_corrupted_checksum_rejected(tmp: Path) -> list[str]:
    """A reprepare whose archive fails the checksum gate must not touch the
    tree `current` already resolves to. This is the integrity check, which
    runs before the publish-branch logic and is unchanged by the candidate."""
    problems: list[str] = []
    root = tmp / "server"
    make_server(root)

    old_files = _minimal_tree("old-content-v1\n")
    build_raw_archive(root, FAKE_SHA_X, old_files, valid_checksum=True)
    proc = prepare_raw(root, FAKE_SHA_X)
    if proc.returncode != 0:
        return [f"baseline prepare of {FAKE_SHA_X} failed:\n{proc.stdout}{proc.stderr}"]
    set_current(root, FAKE_SHA_X)

    old_tree = root / "releases" / FAKE_SHA_X
    old_marker_before = (old_tree / MARKER_NAME).read_text()

    # Re-ship the same SHA with different bytes and a checksum that does not
    # match them (a corrupted transfer, or tampering).
    new_files = _minimal_tree("new-content-v2\n")
    build_raw_archive(root, FAKE_SHA_X, new_files, valid_checksum=False)
    proc_bad = prepare_raw(root, FAKE_SHA_X)

    if proc_bad.returncode == 0:
        problems.append("prepare succeeded despite a checksum mismatch")
    if "checksum" not in (proc_bad.stdout + proc_bad.stderr).lower():
        problems.append(
            "prepare did not fail with a checksum-related message:\n"
            f"{proc_bad.stdout}{proc_bad.stderr}"
        )

    resolved = Path(os.path.realpath(root / "current"))
    if not resolved.is_dir():
        problems.append("current does not resolve to a directory after a failed reprepare")
    elif not (resolved / MARKER_NAME).is_file() or (resolved / MARKER_NAME).read_text() != old_marker_before:
        problems.append(
            "the old release's content changed even though the reprepare failed the checksum gate"
        )

    unlock(root)
    return problems


def check_marker_reuse_skips_replacement(tmp: Path) -> list[str]:
    """Branch 1: the recorded marker matches the incoming archive's digest ->
    the directory is reused untouched and stdout says so."""
    problems: list[str] = []
    root = tmp / "server"
    make_server(root)

    files = _minimal_tree("same-content\n")
    build_raw_archive(root, FAKE_SHA_X, files, valid_checksum=True)
    proc = prepare_raw(root, FAKE_SHA_X)
    if proc.returncode != 0:
        return [f"baseline prepare of {FAKE_SHA_X} failed:\n{proc.stdout}{proc.stderr}"]
    set_current(root, FAKE_SHA_X)

    marker = root / "releases" / ".markers" / FAKE_SHA_X
    if not marker.is_file():
        problems.append("releases/.markers/<sha> was not written by the baseline prepare")

    # Re-ship the exact same bytes: the marker must match and the directory
    # must be reused without ever being removed.
    build_raw_archive(root, FAKE_SHA_X, files, valid_checksum=True)
    proc2 = prepare_raw(root, FAKE_SHA_X)
    if proc2.returncode != 0:
        problems.append(f"reprepare of an identical archive failed:\n{proc2.stdout}{proc2.stderr}")
    elif "reusing" not in proc2.stdout.lower():
        problems.append(
            f"reprepare succeeded but stdout does not mention reuse (marker branch):\n{proc2.stdout}"
        )

    resolved = Path(os.path.realpath(root / "current"))
    if not resolved.is_dir() or not (resolved / MARKER_NAME).is_file() \
            or (resolved / MARKER_NAME).read_text() != "same-content\n":
        problems.append("current does not resolve to the intact, expected tree after a marker-reuse reprepare")

    unlock(root)
    return problems


def check_missing_marker_falls_back_to_diff(tmp: Path) -> list[str]:
    """Branch 2: no marker on disk (or it was lost), but the unpacked tree is
    byte-identical to what's already published -> reused via `diff -r -q`,
    and the marker is (re)written so the fast path applies next time."""
    problems: list[str] = []
    root = tmp / "server"
    make_server(root)

    files = _minimal_tree("same-content\n")
    build_raw_archive(root, FAKE_SHA_X, files, valid_checksum=True)
    proc = prepare_raw(root, FAKE_SHA_X)
    if proc.returncode != 0:
        return [f"baseline prepare of {FAKE_SHA_X} failed:\n{proc.stdout}{proc.stderr}"]
    set_current(root, FAKE_SHA_X)

    marker = root / "releases" / ".markers" / FAKE_SHA_X
    if not marker.is_file():
        return [f"releases/.markers/{FAKE_SHA_X} was not written by the baseline prepare"]
    marker.unlink()  # simulate a tree prepared before the marker existed, or a lost marker

    build_raw_archive(root, FAKE_SHA_X, files, valid_checksum=True)
    proc2 = prepare_raw(root, FAKE_SHA_X)
    if proc2.returncode != 0:
        problems.append(f"reprepare without a marker failed:\n{proc2.stdout}{proc2.stderr}")
    elif "reusing" not in proc2.stdout.lower():
        problems.append(
            f"reprepare succeeded but stdout does not mention reuse (diff -r branch):\n{proc2.stdout}"
        )

    if not marker.is_file():
        problems.append("the marker was not (re)written after a diff -r based reuse")

    resolved = Path(os.path.realpath(root / "current"))
    if not resolved.is_dir() or not (resolved / MARKER_NAME).is_file() \
            or (resolved / MARKER_NAME).read_text() != "same-content\n":
        problems.append("current does not resolve to the intact, expected tree after a diff-based reuse")

    unlock(root)
    return problems


def check_diverged_content_current_target_refuses(tmp: Path) -> list[str]:
    """Branch 3: the same SHA, a validly-checksummed archive, but content
    that differs from what's on disk, while `current` points at that exact
    directory -> refuse with a non-zero exit, leave the directory untouched,
    and keep `current` resolving to it."""
    problems: list[str] = []
    root = tmp / "server"
    make_server(root)

    old_files = _minimal_tree("old-content-v1\n")
    build_raw_archive(root, FAKE_SHA_X, old_files, valid_checksum=True)
    proc = prepare_raw(root, FAKE_SHA_X)
    if proc.returncode != 0:
        return [f"baseline prepare of {FAKE_SHA_X} failed:\n{proc.stdout}{proc.stderr}"]
    set_current(root, FAKE_SHA_X)
    old_marker_before = (root / "releases" / FAKE_SHA_X / MARKER_NAME).read_text()

    # Different content, correct checksum for that content: the checksum
    # gate has nothing to object to, only the publish-branch logic does.
    new_files = _minimal_tree("new-content-v2\n")
    build_raw_archive(root, FAKE_SHA_X, new_files, valid_checksum=True)
    proc2 = prepare_raw(root, FAKE_SHA_X)

    if proc2.returncode == 0:
        problems.append(
            "prepare replaced the release that 'current' points at even though the incoming "
            "archive's content differs from what was published -- this is exactly the hazard "
            "REL-LOCAL-01 exists to prevent"
        )
    if "current" not in (proc2.stdout + proc2.stderr).lower():
        problems.append(
            f"prepare refused but did not explain that 'current' is why:\n{proc2.stdout}{proc2.stderr}"
        )

    resolved = Path(os.path.realpath(root / "current"))
    if not resolved.is_dir():
        problems.append("current does not resolve to a directory after the refusal")
    elif (resolved / MARKER_NAME).read_text() != old_marker_before:
        problems.append("the release's content changed even though prepare refused to replace it")

    unlock(root)
    return problems


# --- REL-SAME-03 -------------------------------------------------------------

def check_concurrent_reprepare_no_mixed_tree(tmp: Path) -> list[str]:
    """Two prepares of the same SHA launched concurrently must not leave a
    tree with files from both attempts mixed together, and must not touch a
    separate release that `current` points at (the rollback target)."""
    problems: list[str] = []
    root = tmp / "server"
    make_server(root)

    # A pre-existing "rollback target" release that current points at and
    # that prepare() must never touch (prepare doesn't flip `current`, but it
    # does prune old releases, and the prune step must still spare it).
    rollback_files = _minimal_tree("rollback-content\n")
    build_raw_archive(root, FAKE_SHA_ROLLBACK, rollback_files, valid_checksum=True)
    proc = prepare_raw(root, FAKE_SHA_ROLLBACK)
    if proc.returncode != 0:
        return [f"baseline prepare of rollback target failed:\n{proc.stdout}{proc.stderr}"]
    set_current(root, FAKE_SHA_ROLLBACK)
    rollback_marker_before = (root / "releases" / FAKE_SHA_ROLLBACK / MARKER_NAME).read_text()

    # One shared archive for SHA X: two concurrent prepares of the exact same
    # bytes, the realistic "the same deploy job got triggered twice" case.
    files = _minimal_tree("concurrent-content\n")
    build_raw_archive(root, FAKE_SHA_X, files, valid_checksum=True)

    def run() -> subprocess.CompletedProcess:
        return prepare_raw(root, FAKE_SHA_X)

    results: list[subprocess.CompletedProcess] = [None, None]  # type: ignore[list-item]

    def worker(idx: int) -> None:
        results[idx] = run()

    t1 = threading.Thread(target=worker, args=(0,))
    t2 = threading.Thread(target=worker, args=(1,))
    t1.start()
    t2.start()
    t1.join(timeout=60)
    t2.join(timeout=60)

    successes = [r for r in results if r is not None and r.returncode == 0]
    failures = [r for r in results if r is not None and r.returncode != 0]

    if not successes:
        problems.append(
            "both concurrent prepares of the same SHA failed:\n"
            + "\n---\n".join(f"{r.stdout}{r.stderr}" for r in results if r is not None)
        )

    # A failure is only acceptable if it is the benign "the other process
    # already consumed/removed the shared incoming archive" race, not data
    # corruption.
    for r in failures:
        combined = (r.stdout + r.stderr).lower()
        if "archive not found" not in combined and "checksum" not in combined and "could not unpack" not in combined:
            problems.append(
                f"a concurrent prepare failed for an unexpected reason:\n{r.stdout}{r.stderr}"
            )

    target = root / "releases" / FAKE_SHA_X
    if successes:
        if not target.is_dir():
            problems.append("no releases/<sha> tree exists after a successful concurrent prepare")
        else:
            got = (target / MARKER_NAME).read_text() if (target / MARKER_NAME).is_file() else None
            if got != "concurrent-content\n":
                problems.append(
                    f"releases/{FAKE_SHA_X}/{MARKER_NAME} reads {got!r}; expected the single source "
                    "archive's content -- a mix would indicate files from two attempts landed in one tree"
                )
            for required in ("infra/production/docker-compose.yml", "infra/production/deploy.sh",
                              "apps/api/Dockerfile", "apps/web/Dockerfile"):
                if not (target / required).is_file():
                    problems.append(f"releases/{FAKE_SHA_X} is missing {required} -- an incomplete/mixed tree")

    leftover_staging = list((root / "releases").glob(".staging-*"))
    if leftover_staging:
        problems.append(f"leftover staging directories were not cleaned up: {leftover_staging}")

    rollback_tree = root / "releases" / FAKE_SHA_ROLLBACK
    if not rollback_tree.is_dir():
        problems.append("the rollback target was removed by a concurrent prepare of a different SHA")
    elif (rollback_tree / MARKER_NAME).read_text() != rollback_marker_before:
        problems.append("the rollback target's content changed even though it was never (re)prepared")

    unlock(root)
    return problems


# --- REL-SAME-04 -------------------------------------------------------------

EXISTING_SUITE_SCRIPTS = [
    TESTS_DIR / "test_release_build_context.py",
    TESTS_DIR / "test_deploy_release_gate.py",
    TESTS_DIR / "test_release_pipeline_wiring.py",
]


def check_existing_suite_still_green(tmp: Path) -> list[str]:
    problems: list[str] = []
    for script in EXISTING_SUITE_SCRIPTS:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
        )
        if proc.returncode != 0:
            problems.append(
                f"{script.name} exited {proc.returncode}:\n{proc.stdout[-3000:]}\n{proc.stderr[-2000:]}"
            )
    return problems


CHECKS = [
    ("REL-SAME-01: reprepare of the SHA `current` already points at never lets a concurrent reader see a missing tree",
     check_reprepare_never_dangles_current),
    ("REL-SAME-02a: a corrupted-checksum reprepare fails and leaves the old release intact",
     check_corrupted_checksum_rejected),
    ("REL-SAME-02b: marker matches the incoming archive -> reused untouched, stdout says 'reusing'",
     check_marker_reuse_skips_replacement),
    ("REL-SAME-02c: no marker but content is identical -> reused via diff -r, marker (re)written",
     check_missing_marker_falls_back_to_diff),
    ("REL-SAME-02d: content diverged from what's on disk while current -> TARGET -> refuse, tree and current intact",
     check_diverged_content_current_target_refuses),
    ("REL-SAME-03: two concurrent prepares of the same SHA never mix trees and never touch the rollback target",
     check_concurrent_reprepare_no_mixed_tree),
    ("REL-SAME-04: the existing infra/production/tests suite is green",
     check_existing_suite_still_green),
]


def main() -> int:
    for tool in ("git", "tar", "bash"):
        if not shutil.which(tool):
            print(f"{tool} is required", file=sys.stderr)
            return 2

    failed = 0
    for i, (name, fn) in enumerate(CHECKS, 1):
        with tempfile.TemporaryDirectory(prefix="drinkx-rel-same-") as tmp:
            try:
                problems = fn(Path(tmp))
            except Exception as exc:  # noqa: BLE001 - report, do not crash the suite
                import traceback
                problems = [f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"]
        status = "PASS" if not problems else "FAIL"
        failed += bool(problems)
        print(f"[{status}] {i}. {name}")
        for problem in problems:
            print(f"      {problem}")

    total = len(CHECKS)
    print(f"\n{total - failed}/{total} checks passed")
    return 1 if failed else 0


# --- pytest entry points -----------------------------------------------------
# infra/production/tests has no conftest.py / pytest.ini of its own; these
# thin wrappers just let `pytest infra/production/tests` pick this file up
# too, reusing the exact same check functions the standalone runner uses.

def test_rel_same_01_reprepare_never_dangles_current() -> None:
    with tempfile.TemporaryDirectory(prefix="drinkx-rel-same-") as tmp:
        problems = check_reprepare_never_dangles_current(Path(tmp))
    assert not problems, "\n".join(problems)


def test_rel_same_02a_corrupted_checksum_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="drinkx-rel-same-") as tmp:
        problems = check_corrupted_checksum_rejected(Path(tmp))
    assert not problems, "\n".join(problems)


def test_rel_same_02b_marker_reuse_skips_replacement() -> None:
    with tempfile.TemporaryDirectory(prefix="drinkx-rel-same-") as tmp:
        problems = check_marker_reuse_skips_replacement(Path(tmp))
    assert not problems, "\n".join(problems)


def test_rel_same_02c_missing_marker_falls_back_to_diff() -> None:
    with tempfile.TemporaryDirectory(prefix="drinkx-rel-same-") as tmp:
        problems = check_missing_marker_falls_back_to_diff(Path(tmp))
    assert not problems, "\n".join(problems)


def test_rel_same_02d_diverged_content_current_target_refuses() -> None:
    with tempfile.TemporaryDirectory(prefix="drinkx-rel-same-") as tmp:
        problems = check_diverged_content_current_target_refuses(Path(tmp))
    assert not problems, "\n".join(problems)


def test_rel_same_03_concurrent_reprepare_no_mixed_tree() -> None:
    with tempfile.TemporaryDirectory(prefix="drinkx-rel-same-") as tmp:
        problems = check_concurrent_reprepare_no_mixed_tree(Path(tmp))
    assert not problems, "\n".join(problems)


def test_rel_same_04_existing_suite_still_green() -> None:
    with tempfile.TemporaryDirectory(prefix="drinkx-rel-same-") as tmp:
        problems = check_existing_suite_still_green(Path(tmp))
    assert not problems, "\n".join(problems)


if __name__ == "__main__":
    raise SystemExit(main())
