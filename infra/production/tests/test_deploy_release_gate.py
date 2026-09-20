#!/usr/bin/env python3
"""Regression tests for the production deploy release gate (audit G1 / BUG-01).

The pre-G1 script swallowed a failed image build, fell through to health checks
that the still-running OLD release answered happily, and exited 0. An operator
saw a green deploy while the fix never reached production.

These tests run the real `infra/production/deploy.sh` with `docker`, `curl` and
`sleep` replaced by local stubs on PATH. No Docker daemon, no SSH, no HTTP, no
production host is touched. Run:

    python3 infra/production/tests/test_deploy_release_gate.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[2]
DEPLOY_SH = REPO_ROOT / "infra" / "production" / "deploy.sh"
STUB_BIN = TESTS_DIR / "stub_bin"

EXPECTED_SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
OLD_SHA = "9988776655443322110099887766554433221100"

SUCCESS_MARKER = "DEPLOY_RESULT=success"


@dataclass
class Scenario:
    name: str
    stubs: dict[str, str]
    expect_success: bool
    why: str
    deploy_sha: str = EXPECTED_SHA
    must_contain: list[str] = field(default_factory=list)


def all_healthy(sha: str = EXPECTED_SHA) -> dict[str, str]:
    return {
        "STUB_BUILD_RC": "0",
        "STUB_UP_RC": "0",
        "STUB_RUNNING_SHA": sha,
        "STUB_API_HEALTH": "ok",
        "STUB_WEB_HEALTH": "ok",
        "STUB_WORKER_PING": "ok",
        "STUB_BEAT_RUNNING": "yes",
    }


SCENARIOS = [
    Scenario(
        name="build fails (rc=17) while the old release stays fully healthy",
        stubs={**all_healthy(OLD_SHA), "STUB_BUILD_RC": "17"},
        expect_success=False,
        why="a failed build must fail the deploy even when the old release answers every probe",
    ),
    Scenario(
        name="build succeeds but the running containers report a different SHA",
        stubs=all_healthy(OLD_SHA),
        expect_success=False,
        why="healthy-but-stale must not count as a delivered release",
    ),
    Scenario(
        name="api and web healthy, celery worker does not answer ping",
        stubs={**all_healthy(), "STUB_WORKER_PING": "fail"},
        expect_success=False,
        why="background jobs down is a failed deploy",
    ),
    Scenario(
        name="api and worker healthy, beat container not running",
        stubs={**all_healthy(), "STUB_BEAT_RUNNING": "no"},
        expect_success=False,
        why="no beat means no scheduled jobs",
    ),
    Scenario(
        name="api health never answers within the retry budget",
        stubs={**all_healthy(), "STUB_API_HEALTH": "fail"},
        expect_success=False,
        why="an exhausted retry budget is a failure, not a warning",
    ),
    Scenario(
        name="every component healthy and stamped with the expected SHA",
        stubs=all_healthy(),
        expect_success=True,
        why="the only path that may report success",
        must_contain=[SUCCESS_MARKER],
    ),
    Scenario(
        name="manual run with no DEPLOY_SHA: healthy, but nothing to verify against",
        stubs=all_healthy(),
        deploy_sha="",
        expect_success=True,
        why="a hand-run deploy may finish, but must never claim a verified release",
        must_contain=["DEPLOY_RESULT=unverified"],
    ),
]


# --- static contract checks -------------------------------------------------
# The version stamp is only evidence if it is baked into the image. If it were
# also a compose `environment:` value, restarting a stale image with a fresh
# variable would satisfy every runtime check above without rebuilding anything.

COMPOSE = REPO_ROOT / "infra" / "production" / "docker-compose.yml"
API_DOCKERFILE = REPO_ROOT / "apps" / "api" / "Dockerfile"
WEB_DOCKERFILE = REPO_ROOT / "apps" / "web" / "Dockerfile"


def static_checks() -> list[str]:
    problems: list[str] = []

    compose = COMPOSE.read_text()
    for line in compose.splitlines():
        stripped = line.strip()
        if stripped.startswith("DRINKX_GIT_SHA"):
            problems.append(
                "docker-compose.yml sets DRINKX_GIT_SHA as a runtime value; "
                "it must only ever be a build arg"
            )
    if compose.count("GIT_SHA: ${DEPLOY_SHA:-unknown}") != 4:
        problems.append(
            "expected the GIT_SHA build arg on all four built services "
            "(api, worker, beat, web)"
        )

    for label, path in (("api", API_DOCKERFILE), ("web", WEB_DOCKERFILE)):
        text = path.read_text()
        if "ARG GIT_SHA" not in text:
            problems.append(f"{label} Dockerfile does not declare ARG GIT_SHA")
        if "ENV DRINKX_GIT_SHA=${GIT_SHA}" not in text:
            problems.append(f"{label} Dockerfile does not bake DRINKX_GIT_SHA into the image")

    return problems


def run_scenario(sc: Scenario) -> tuple[bool, str]:
    """Run deploy.sh under the scenario. Returns (passed, report)."""
    bash = shutil.which("bash")
    if not bash:
        raise SystemExit("bash is required")

    with tempfile.TemporaryDirectory(prefix="drinkx-g1-") as tmp:
        work = Path(tmp)
        script = work / "infra" / "production" / "deploy.sh"
        script.parent.mkdir(parents=True)
        shutil.copy2(DEPLOY_SH, script)

        mocks = work / "stub-bin"
        mocks.mkdir()
        for name in ("docker", "curl", "sleep"):
            target = mocks / name
            shutil.copy2(STUB_BIN / name, target)
            target.chmod(0o755)

        env = dict(os.environ)
        env["PATH"] = f"{mocks}{os.pathsep}" + env.get("PATH", "/usr/bin:/bin")
        env["DEPLOY_SHA"] = sc.deploy_sha
        env.update(sc.stubs)

        proc = subprocess.run(
            [bash, str(script)],
            env=env,
            cwd=work,
            capture_output=True,
            text=True,
            timeout=120,
        )

    output = proc.stdout + proc.stderr
    problems = []

    if sc.expect_success:
        if proc.returncode != 0:
            problems.append(f"expected exit 0, got {proc.returncode}")
    else:
        if proc.returncode == 0:
            problems.append("expected a non-zero exit, got 0")
        if SUCCESS_MARKER in output:
            problems.append(f"a failed deploy printed the success marker {SUCCESS_MARKER!r}")

    for needle in sc.must_contain:
        if needle not in output:
            problems.append(f"missing expected output {needle!r}")

    report = f"exit={proc.returncode}"
    if problems:
        report += "\n      " + "\n      ".join(problems)
        report += "\n      --- script output ---\n"
        report += "\n".join(f"      | {line}" for line in output.strip().splitlines())
    return (not problems), report


def main() -> int:
    if not DEPLOY_SH.is_file():
        raise SystemExit(f"not found: {DEPLOY_SH}")

    print(f"deploy script : {DEPLOY_SH}")
    print(f"expected SHA  : {EXPECTED_SHA}")
    print()

    failed = 0
    for i, sc in enumerate(SCENARIOS, 1):
        passed, report = run_scenario(sc)
        status = "PASS" if passed else "FAIL"
        if not passed:
            failed += 1
        print(f"[{status}] {i}. {sc.name}")
        print(f"      expectation: {'success' if sc.expect_success else 'failure'} — {sc.why}")
        print(f"      {report}")
        print()

    total = len(SCENARIOS)
    print(f"{total - failed}/{total} scenarios passed")

    static_problems = static_checks()
    if static_problems:
        print("\n[FAIL] static contract checks")
        for problem in static_problems:
            print(f"      {problem}")
        failed += 1
    else:
        print("[PASS] static contract checks: the version stamp is build-time only")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
