#!/usr/bin/env python3
"""Reproduction of DEBT-01: the production build context was not the commit.

Nothing here touches the real server, and no Docker daemon is required. A
throwaway git repository plays the role of the project, a temporary directory
plays the role of /opt/drinkx-crm, and `rsync` is the same rsync the workflow
used to run.

Four steps, in the order the audit asks for them:

  1. release A contains apps/api/app/legacy_provider.py;
  2. release B deletes that file from git and adds apps/api/app/new_provider.py;
  3. the OLD delivery (`rsync -az` with no --delete) leaves the deleted file on
     the server, so it is still sitting in the build context of release B;
  4. whether the Dockerfile's COPY would then bake it into the image is read
     off the Dockerfile — building an image is NOT RUN here, no daemon.

Then the same A -> B sequence through the G4 delivery (`git archive` unpacked
into an empty per-SHA directory), where the file is gone.

Run:  python3 infra/production/tests/repro_build_context_debt01.py
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
API_DOCKERFILE = REPO_ROOT / "apps" / "api" / "Dockerfile"

STALE = "apps/api/app/legacy_provider.py"
FRESH = "apps/api/app/new_provider.py"

findings: list[str] = []
notrun: list[str] = []


def say(msg: str = "") -> None:
    print(msg)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def build_repo(repo: Path) -> tuple[str, str]:
    """Two releases: A has the legacy file, B deletes it and adds a new one."""
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "repro@example.invalid")
    git(repo, "config", "user.name", "repro")

    # Enough of the real layout for the delivery scripts to accept the tree.
    for rel, body in (
        ("infra/production/docker-compose.yml", "name: drinkx\n"),
        ("infra/production/deploy.sh", "#!/usr/bin/env bash\n"),
        ("apps/api/Dockerfile", "FROM scratch\nCOPY apps/api/app ./app\n"),
        ("apps/web/Dockerfile", "FROM scratch\n"),
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
    git(repo, "commit", "-qm", "release B: drop the legacy provider")
    sha_b = git(repo, "rev-parse", "HEAD")
    return sha_a, sha_b


def old_delivery(repo: Path, server_root: Path) -> None:
    """What .github/workflows/deploy.yml did before G4."""
    subprocess.run(
        [
            "rsync", "-a",
            "--exclude=.git/",
            "--exclude=.env",
            "--exclude=.env.*",
            "--exclude=infra/production/.env",
            f"{repo}/", f"{server_root}/",
        ],
        check=True,
        capture_output=True,
    )


def new_delivery(repo: Path, server_root: Path, sha: str) -> subprocess.CompletedProcess:
    """What it does after G4: archive the commit, unpack into releases/<sha>."""
    incoming = server_root / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    archive = incoming / f"{sha}.tar.gz"
    subprocess.run(
        ["bash", str(MAKE_ARCHIVE), sha, str(archive), str(repo)],
        check=True, capture_output=True, text=True,
    )
    env = dict(os.environ, DEPLOY_ROOT=str(server_root))
    return subprocess.run(
        ["bash", str(PREPARE), sha],
        env=env, capture_output=True, text=True,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="drinkx-g4-repro-") as tmp:
        tmp_path = Path(tmp)
        repo = tmp_path / "repo"
        sha_a, sha_b = build_repo(repo)

        say("=" * 72)
        say("DEBT-01 reproduction — was the production build context the commit?")
        say("=" * 72)
        say(f"release A : {sha_a}  has {STALE}")
        say(f"release B : {sha_b}  deletes it, adds {FRESH}")
        say()

        # -- step 1/2/3: the old delivery -------------------------------------
        server = tmp_path / "old-server"
        server.mkdir()
        # Server-owned state that lives in the same directory and is the reason
        # --delete was never an option there.
        (server / "infra" / "production").mkdir(parents=True)
        (server / "infra" / "production" / ".env").write_text("POSTGRES_PASSWORD=real\n")

        git(repo, "checkout", "-q", sha_a)
        old_delivery(repo, server)
        step1 = (server / STALE).is_file()
        say(f"[1] after release A the server has {STALE}: {step1}")

        git(repo, "checkout", "-q", sha_b)
        say(f"[2] in release B, git no longer tracks it: "
            f"{STALE not in git(repo, 'ls-tree', '-r', '--name-only', sha_b).splitlines()}")

        old_delivery(repo, server)
        stale_survived = (server / STALE).is_file()
        fresh_arrived = (server / FRESH).is_file()
        say(f"[3] after release B, rsync without --delete leaves it on disk: {stale_survived}")
        say(f"    the new file did arrive: {fresh_arrived}")
        say(f"    .env survived too, which is why --delete was never used here: "
            f"{(server / 'infra' / 'production' / '.env').is_file()}")

        if not stale_survived:
            findings.append("rsync without --delete did NOT leave the deleted file — repro failed")
        if not fresh_arrived:
            findings.append("the new file did not arrive over rsync — repro is not modelling delivery")

        # -- step 4: would the COPY pick it up? -------------------------------
        say()
        dockerfile = API_DOCKERFILE.read_text()
        copies = [
            line.strip() for line in dockerfile.splitlines()
            if line.strip().startswith("COPY ") and "--from=" not in line
        ]
        say("[4] apps/api/Dockerfile copies whole directories out of that context:")
        for line in copies:
            say(f"      {line}")
        covered = any(
            line.split()[1] == "apps/api/app" for line in copies
        )
        say(f"    {STALE} sits under `apps/api/app`, which is copied wholesale: {covered}")
        say("    NOT RUN: no Docker daemon in this environment, so the image was")
        say("    not built and the file was not listed inside it. The claim above")
        say("    is read off the Dockerfile, not observed in an image.")
        notrun.append("docker build of apps/api/Dockerfile to list the stale file inside the image")
        if not covered:
            findings.append(
                "apps/api/Dockerfile no longer copies apps/api/app wholesale — "
                "re-check whether this reproduction still describes the delivery"
            )

        # -- the same A -> B through the G4 delivery --------------------------
        say()
        say("-" * 72)
        say("Same two releases through the G4 delivery")
        say("-" * 72)
        new_server = tmp_path / "new-server"
        (new_server / "shared").mkdir(parents=True)
        (new_server / "shared" / ".env").write_text("POSTGRES_PASSWORD=real\n")

        for sha, label in ((sha_a, "A"), (sha_b, "B")):
            proc = new_delivery(repo, new_server, sha)
            if proc.returncode != 0:
                findings.append(f"preparing release {label} failed: {proc.stderr.strip()}")
                say(proc.stdout + proc.stderr)
                break
            tree = new_server / "releases" / sha
            say(f"release {label} -> {tree.relative_to(new_server)}")
            say(f"    {STALE} present: {(tree / STALE).is_file()}")
            say(f"    {FRESH} present: {(tree / FRESH).is_file()}")
        else:
            tree_b = new_server / "releases" / sha_b
            if (tree_b / STALE).exists():
                findings.append("the deleted file is still in the G4 build context")
            if not (tree_b / FRESH).is_file():
                findings.append("the new file is missing from the G4 build context")
            if list(tree_b.rglob(".env")):
                findings.append(".env leaked into the G4 build context")
            say()
            say(f"    secrets stayed outside the tree: "
                f"{(new_server / 'shared' / '.env').is_file() and not list(tree_b.rglob('.env'))}")
            say(f"    releases A and B are separate directories: "
                f"{(new_server / 'releases' / sha_a).is_dir()}")

        # release A's tree is read-only after publication; let TemporaryDirectory clean up
        for path in (new_server / "releases").glob("*"):
            subprocess.run(["chmod", "-R", "u+w", str(path)], check=False)

    say()
    if findings:
        say("[FAIL] reproduction")
        for f in findings:
            say(f"      {f}")
        return 1
    say("[PASS] reproduction: the old delivery keeps a deleted file in the build")
    say("       context; the G4 delivery does not.")
    for n in notrun:
        say(f"       NOT RUN: {n}")
    return 0


if __name__ == "__main__":
    # rsync models the delivery that caused DEBT-01. Without it the
    # reproduction cannot run — but this is evidence, not a gate, so a runner
    # image that drops rsync must not block every release.
    if not shutil.which("rsync"):
        print("SKIPPED: rsync is not installed, the old delivery cannot be reproduced here")
        raise SystemExit(0)
    raise SystemExit(main())
