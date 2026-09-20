#!/usr/bin/env python3
"""The production build context must be exactly the tree of the released commit.

Audit G4 / DEBT-01. Delivery used to be `rsync` without --delete into one
long-lived /opt/drinkx-crm, so a file deleted from git survived on the server
and the Dockerfile's directory-level COPYs could still bake it into an image.
The OCI revision label proved which GIT_SHA a build was *asked* for, not which
tree it was built *from*.

Everything below runs against throwaway git repositories and temporary
directories. No Docker daemon, no SSH, no network, no production host.

    python3 infra/production/tests/test_release_build_context.py

The reproduction of the original defect lives next door in
repro_build_context_debt01.py.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[2]
MAKE_ARCHIVE = REPO_ROOT / "infra" / "production" / "make_release_archive.sh"
PREPARE = REPO_ROOT / "infra" / "production" / "remote_prepare_release.sh"
DEPLOY_SH = REPO_ROOT / "infra" / "production" / "deploy.sh"
STUB_BIN = TESTS_DIR / "stub_bin"
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"

STALE = "apps/api/app/legacy_provider.py"
FRESH = "apps/api/app/new_provider.py"
SECRET_BODY = "POSTGRES_PASSWORD=real-production-password\n"


# --- helpers ---------------------------------------------------------------

def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def make_repo(repo: Path) -> tuple[str, str]:
    """Release A holds STALE; release B deletes it and adds FRESH."""
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "test")
    for rel, body in (
        ("infra/production/docker-compose.yml", "name: drinkx\n"),
        ("infra/production/deploy.sh", "#!/usr/bin/env bash\n"),
        ("apps/api/Dockerfile", "FROM scratch\nCOPY apps/api/app ./app\n"),
        ("apps/web/Dockerfile", "FROM scratch\n"),
        ("infra/production/.env.example", "POSTGRES_PASSWORD=changeme\n"),
        (STALE, "PROVIDER = 'legacy'\n"),
        # A non-ASCII name on purpose: `git ls-tree` C-escapes those unless
        # core.quotePath=false, while tar prints raw bytes. The archive's own
        # self-check compares the two lists, and the default made it disagree
        # with itself on every real tree (this repository has two such files).
        ("docs/\u0420\u0423\u041a\u041e\u0412\u041e\u0414\u0421\u0422\u0412\u041e.md", "\u0442\u0435\u043a\u0441\u0442\n"),
        (".gitignore", ".env\n"),
    ):
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "release A")
    sha_a = git(repo, "rev-parse", "HEAD")

    (repo / STALE).unlink()
    (repo / FRESH).write_text("PROVIDER = 'new'\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "release B")
    sha_b = git(repo, "rev-parse", "HEAD")
    return sha_a, sha_b


def make_server(root: Path) -> None:
    """A deploy root with the secrets where G4 expects them: outside releases."""
    (root / "shared").mkdir(parents=True)
    (root / "shared" / ".env").write_text(SECRET_BODY)


def archive(repo: Path, root: Path, sha: str) -> Path:
    out = root / "incoming" / f"{sha}.tar.gz"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["bash", str(MAKE_ARCHIVE), sha, str(out), str(repo)],
        check=True, capture_output=True, text=True,
    )
    return out


def prepare(root: Path, sha: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(PREPARE), sha],
        env=dict(os.environ, DEPLOY_ROOT=str(root)),
        capture_output=True, text=True, timeout=120,
    )


def release_a_then_b(tmp: Path) -> tuple[Path, Path, str, str]:
    """The full A -> B sequence through the real delivery scripts."""
    repo = tmp / "repo"
    sha_a, sha_b = make_repo(repo)
    root = tmp / "server"
    make_server(root)
    for sha in (sha_a, sha_b):
        archive(repo, root, sha)
        proc = prepare(root, sha)
        if proc.returncode != 0:
            raise AssertionError(f"preparing {sha} failed:\n{proc.stdout}{proc.stderr}")
    return repo, root, sha_a, sha_b


def unlock(root: Path) -> None:
    """Published release trees are read-only; let the temp dir be removed."""
    releases = root / "releases"
    if releases.is_dir():
        subprocess.run(["chmod", "-R", "u+w", str(releases)], check=False)


# --- the checks ------------------------------------------------------------

def check_deleted_file_is_gone(tmp: Path) -> list[str]:
    """A file deleted between A and B must not be in B's build context."""
    _, root, sha_a, sha_b = release_a_then_b(tmp)
    problems = []
    if not (root / "releases" / sha_a / STALE).is_file():
        problems.append(f"release A does not contain {STALE} — the fixture proves nothing")
    if (root / "releases" / sha_b / STALE).exists():
        problems.append(
            f"{STALE} was deleted in release B but is still in its build context — "
            "this is DEBT-01, unfixed"
        )
    unlock(root)
    return problems


def check_new_file_is_present(tmp: Path) -> list[str]:
    """Delivering only what the commit tracks must still deliver all of it."""
    _, root, _, sha_b = release_a_then_b(tmp)
    problems = []
    if not (root / "releases" / sha_b / FRESH).is_file():
        problems.append(f"{FRESH} was added in release B but is missing from its build context")
    unlock(root)
    return problems


def check_context_equals_the_commit(tmp: Path) -> list[str]:
    """Not a subset and not a superset: exactly `git ls-tree -r <sha>`."""
    repo, root, _, sha_b = release_a_then_b(tmp)
    tree = root / "releases" / sha_b
    # -c core.quotePath=false, or git C-escapes the non-ASCII name above and
    # the comparison disagrees with the filesystem rather than with the tree.
    expected = set(
        git(repo, "-c", "core.quotePath=false", "ls-tree", "-r", "--name-only", sha_b).splitlines()
    )
    actual = {
        str(p.relative_to(tree)) for p in tree.rglob("*") if p.is_file() or p.is_symlink()
    }
    problems = []
    for extra in sorted(actual - expected):
        problems.append(f"build context holds {extra}, which is not in the commit")
    for missing in sorted(expected - actual):
        problems.append(f"build context is missing {missing}, which the commit tracks")
    unlock(root)
    return problems


def check_secrets_stay_out(tmp: Path) -> list[str]:
    """.env must reach neither the archive nor the build context."""
    repo = tmp / "repo"
    sha_a, sha_b = make_repo(repo)
    # The operator's secrets, sitting in the working directory exactly where
    # the legacy layout kept them.
    (repo / "infra" / "production" / ".env").write_text(SECRET_BODY)
    (repo / "apps" / "web").mkdir(parents=True, exist_ok=True)
    (repo / "apps" / "web" / ".env.local").write_text(SECRET_BODY)

    root = tmp / "server"
    make_server(root)
    tar = archive(repo, root, sha_b)
    listing = subprocess.run(
        ["tar", "-tzf", str(tar)], check=True, capture_output=True, text=True
    ).stdout.split()
    problems = []
    for entry in listing:
        name = entry.rstrip("/").rsplit("/", 1)[-1]
        if name == ".env" or (name.startswith(".env.") and not name.endswith(".example")):
            problems.append(f"the release archive carries {entry}")

    proc = prepare(root, sha_b)
    if proc.returncode != 0:
        problems.append(f"preparing the release failed:\n{proc.stdout}{proc.stderr}")
    else:
        tree = root / "releases" / sha_b
        for leaked in tree.rglob(".env*"):
            if not leaked.name.endswith(".example"):
                problems.append(f"the build context carries {leaked.relative_to(tree)}")
        if (root / "shared" / ".env").read_text() != SECRET_BODY:
            problems.append("preparing a release damaged the server's own .env")

    # And the second layer, for anyone building outside this pipeline: the web
    # image does `COPY . .`, so its context needs an ignore file of its own.
    for label, path in (
        ("repository root", REPO_ROOT / ".dockerignore"),
        ("apps/web", REPO_ROOT / "apps" / "web" / ".dockerignore"),
    ):
        if not path.is_file():
            problems.append(f"{label} has no .dockerignore, so a stray .env can enter a build context")
            continue
        text = path.read_text()
        if ".env" not in text:
            problems.append(f"{label} .dockerignore does not exclude .env files")

    unlock(root)
    return problems


def check_untracked_server_file_is_dropped(tmp: Path) -> list[str]:
    """Anything the server grew on its own must not enter the next context."""
    repo = tmp / "repo"
    _, sha_b = make_repo(repo)
    # Untracked in the checkout CI builds the archive from...
    (repo / "apps" / "api" / "app" / "debug_patch.py").write_text("HOTFIX = True\n")
    (repo / "operator_notes.txt").write_text("touched the box by hand\n")

    root = tmp / "server"
    make_server(root)
    # ...and lying around on the server from an earlier hand-edit.
    stray_root = root / "leftover_from_a_manual_fix.py"
    stray_root.write_text("x = 1\n")

    problems = []
    archive(repo, root, sha_b)
    proc = prepare(root, sha_b)
    if proc.returncode != 0:
        problems.append(f"preparing the release failed:\n{proc.stdout}{proc.stderr}")
    else:
        tree = root / "releases" / sha_b
        for stray in ("apps/api/app/debug_patch.py", "operator_notes.txt",
                      "leftover_from_a_manual_fix.py"):
            if (tree / stray).exists():
                problems.append(f"untracked file {stray} reached the build context")
        # Server-owned state outside the release tree is not ours to delete:
        # this is why the fix is a per-SHA directory and not `rsync --delete`.
        if not stray_root.is_file():
            problems.append(
                "preparing a release deleted a file from the deploy root — "
                "volumes, logs and secrets live there"
            )
    unlock(root)
    return problems


def check_failed_preparation_keeps_the_release(tmp: Path) -> list[str]:
    """A broken release must not disturb the one that is serving traffic."""
    repo = tmp / "repo"
    sha_a, sha_b = make_repo(repo)
    root = tmp / "server"
    make_server(root)

    archive(repo, root, sha_a)
    if prepare(root, sha_a).returncode != 0:
        unlock(root)
        return ["could not prepare the baseline release"]
    # deploy.sh publishes this pointer after a verified release.
    (root / "current").symlink_to(root / "releases" / sha_a)

    def truncate(path: Path) -> None:
        path.write_bytes(path.read_bytes()[: len(path.read_bytes()) // 2])

    def not_a_tarball(path: Path) -> None:
        path.write_bytes(b"not a tar file at all\n")

    def rechecksum(path: Path) -> None:
        """Damage the archive *and* its checksum.

        Without this the checksum step rejects the archive first and the
        unpack path is never exercised — a mutation that let a half-extracted
        tree be published went unnoticed until this case existed.
        """
        truncate(path)
        digest = subprocess.run(
            ["shasum", "-a", "256", str(path)] if shutil.which("shasum")
            else ["sha256sum", str(path)],
            check=True, capture_output=True, text=True,
        ).stdout.split()[0]
        Path(f"{path}.sha256").write_text(digest + "\n")

    def missing_tree(path: Path) -> None:
        """A well-formed tarball that is not a release: no compose file."""
        staging = path.parent / "handmade"
        (staging / "docs").mkdir(parents=True, exist_ok=True)
        (staging / "docs" / "note.md").write_text("only docs\n")
        subprocess.run(["tar", "-czf", str(path), "-C", str(staging), "."], check=True)
        Path(f"{path}.sha256").unlink(missing_ok=True)

    problems = []
    cases = [
        ("truncated archive", truncate),
        ("archive that is not a tarball", not_a_tarball),
        ("truncated archive with a matching checksum", rechecksum),
        ("a tarball that is not a release tree", missing_tree),
    ]
    for name, corrupt in cases:
        tar = archive(repo, root, sha_b)
        corrupt(tar)
        proc = prepare(root, sha_b)
        if proc.returncode == 0:
            problems.append(f"{name}: preparation reported success")
        if "RELEASE_PREPARE=ok" in proc.stdout:
            problems.append(f"{name}: preparation printed the success marker")
        if (root / "releases" / sha_b).exists():
            problems.append(f"{name}: a half-unpacked tree was published as releases/<sha>")
        target = os.path.realpath(root / "current")
        if target != os.path.realpath(root / "releases" / sha_a):
            problems.append(f"{name}: `current` moved off the running release to {target}")
        if not (root / "releases" / sha_a / STALE).is_file():
            problems.append(f"{name}: the running release's tree was damaged")
        if (root / "shared" / ".env").read_text() != SECRET_BODY:
            problems.append(f"{name}: the server's .env was damaged")
        for leftover in (root / "releases").glob(".staging-*"):
            problems.append(f"{name}: left scratch directory {leftover.name} behind")

    # A SHA-shaped argument is the only thing that may name a directory.
    for bad in ("../../etc", "HEAD", "deadbeef", ""):
        proc = prepare(root, bad)
        if proc.returncode == 0:
            problems.append(f"preparation accepted {bad!r} as a commit SHA")

    unlock(root)
    return problems


def check_deploy_refuses_an_accumulating_tree(tmp: Path) -> list[str]:
    """deploy.sh must not call a build verified unless it is a prepared release.

    Runs the real script with docker/curl/sleep stubbed, as the G1 gate tests
    do — see test_deploy_release_gate.py.
    """
    sha = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
    problems = []

    def run(tree: Path, deploy_root: Path, stubs: dict[str, str]) -> subprocess.CompletedProcess:
        script = tree / "infra" / "production" / "deploy.sh"
        script.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DEPLOY_SH, script)
        mocks = deploy_root / "stub-bin"
        mocks.mkdir(exist_ok=True)
        for name in ("docker", "curl", "sleep"):
            target = mocks / name
            shutil.copy2(STUB_BIN / name, target)
            target.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = f"{mocks}{os.pathsep}" + env.get("PATH", "/usr/bin:/bin")
        env["DEPLOY_SHA"] = sha
        env.update(stubs)
        return subprocess.run(
            ["bash", str(script)], env=env, cwd=deploy_root,
            capture_output=True, text=True, timeout=180,
        )

    healthy = {
        "STUB_BUILD_RC": "0", "STUB_UP_RC": "0",
        "STUB_BUILD_REV": sha, "STUB_RUN_REV": sha,
        "STUB_API_HEALTH": "ok", "STUB_WEB_HEALTH": "ok",
        "STUB_WORKER_PING": "ok", "STUB_BEAT_RUNNING": "yes",
    }

    # 1. The legacy layout: the script sitting in an accumulating checkout.
    inplace_root = tmp / "inplace"
    (inplace_root / "shared").mkdir(parents=True)
    (inplace_root / "shared" / ".env").write_text(SECRET_BODY)
    proc = run(inplace_root, inplace_root, healthy)
    if proc.returncode == 0:
        problems.append(
            "deploy.sh verified a release built from an accumulating checkout — "
            "that is exactly the context DEBT-01 could not vouch for"
        )
    if "DEPLOY_RESULT=success" in proc.stdout + proc.stderr:
        problems.append("an in-place build printed the success marker")

    # 2. A prepared release tree, everything else identical.
    root = tmp / "prepared"
    (root / "shared").mkdir(parents=True)
    (root / "shared" / ".env").write_text(SECRET_BODY)
    tree = root / "releases" / sha
    proc = run(tree, root, healthy)
    out = proc.stdout + proc.stderr
    if proc.returncode != 0 or "DEPLOY_RESULT=success" not in out:
        problems.append(f"a prepared release tree did not deploy (exit {proc.returncode}):\n{out}")
    if os.path.realpath(root / "current") != os.path.realpath(tree):
        problems.append("a verified release did not publish `current`")

    # 3. Same tree, failing build: `current` must stay where it was.
    (root / "releases" / "previous").mkdir(parents=True, exist_ok=True)
    os.remove(root / "current")
    (root / "current").symlink_to(root / "releases" / "previous")
    proc = run(tree, root, {**healthy, "STUB_BUILD_RC": "17"})
    if proc.returncode == 0:
        problems.append("a failed build reported success")
    if os.path.realpath(root / "current") != os.path.realpath(root / "releases" / "previous"):
        problems.append("a failed build moved `current` off the running release")

    # 4. No environment file anywhere: fail before touching anything.
    bare = tmp / "bare"
    bare_tree = bare / "releases" / sha
    proc = run(bare_tree, bare, healthy)
    if proc.returncode == 0:
        problems.append("deploy.sh ran without an environment file")

    return problems


def check_workflow_ships_a_release_tree() -> list[str]:
    """Structural: the workflow must not go back to syncing a working directory."""
    text = DEPLOY_WORKFLOW.read_text()
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    problems = []
    if "rsync" in code:
        problems.append(
            "deploy.yml rsyncs into the server again; a sync of a working "
            "directory cannot guarantee the build context is the commit"
        )
    if "make_release_archive.sh" not in code:
        problems.append("deploy.yml does not build the release archive from the commit")
    if "remote_prepare_release.sh" not in code:
        problems.append("deploy.yml does not unpack the release into a clean per-SHA tree")
    if "/releases/${{ github.sha }}/infra/production/deploy.sh" not in code:
        problems.append("deploy.yml does not run the deploy script from the prepared release tree")
    return problems


CHECKS = [
    ("a file deleted between A and B is absent from B's build context", check_deleted_file_is_gone),
    ("a file added in B is present in B's build context", check_new_file_is_present),
    ("the build context is exactly the commit's tree", check_context_equals_the_commit),
    ("secrets reach neither the archive nor the build context", check_secrets_stay_out),
    ("untracked files on the server never enter a build context", check_untracked_server_file_is_dropped),
    ("a failed preparation leaves the running release alone", check_failed_preparation_keeps_the_release),
    ("deploy.sh refuses to verify a build from an accumulating tree", check_deploy_refuses_an_accumulating_tree),
]


def main() -> int:
    for tool in ("git", "tar", "bash"):
        if not shutil.which(tool):
            print(f"{tool} is required", file=sys.stderr)
            return 2

    failed = 0
    for i, (name, fn) in enumerate(CHECKS, 1):
        with tempfile.TemporaryDirectory(prefix="drinkx-g4-") as tmp:
            try:
                problems = fn(Path(tmp))
            except Exception as exc:  # noqa: BLE001 - report, do not crash the suite
                problems = [f"{type(exc).__name__}: {exc}"]
        status = "PASS" if not problems else "FAIL"
        failed += bool(problems)
        print(f"[{status}] {i}. {name}")
        for problem in problems:
            print(f"      {problem}")

    problems = check_workflow_ships_a_release_tree()
    status = "PASS" if not problems else "FAIL"
    failed += bool(problems)
    print(f"[{status}] {len(CHECKS) + 1}. the release workflow ships an archive, not a directory sync")
    for problem in problems:
        print(f"      {problem}")

    total = len(CHECKS) + 1
    print(f"\n{total - failed}/{total} checks passed")
    print("note: no image is built here — that the COPY layers then contain only")
    print("      this tree is covered by infra/production/tests/check_image_identity.sh")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
