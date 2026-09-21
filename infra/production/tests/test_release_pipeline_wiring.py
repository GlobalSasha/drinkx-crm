#!/usr/bin/env python3
"""The release pipeline must not be able to ship an unchecked commit.

These are structural assertions over the workflow files. They cannot prove a
run behaves correctly on GitHub — only a real run does that — but they do catch
the ways this wiring silently rots: a path filter that makes a mandatory job
vanish, a gate that treats a skipped prerequisite as approval, secrets handed
to pull-request code, or a deploy job that stops depending on the gate.

Run:  python3 infra/production/tests/test_release_pipeline_wiring.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required to check the workflow wiring", file=sys.stderr)
    raise SystemExit(2)

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

MANDATORY_JOBS = ["api", "migrations", "web", "release-gate", "docker-smoke"]


def load(name: str) -> dict:
    with (WORKFLOWS / name).open() as fh:
        return yaml.safe_load(fh)


def triggers(wf: dict) -> dict:
    # PyYAML reads the bare key `on` as the boolean True.
    return wf.get("on") or wf.get(True) or {}


def check_quality(problems: list[str]) -> None:
    wf = load("quality.yml")
    jobs = wf.get("jobs", {})

    on = triggers(wf)
    if "workflow_call" not in on:
        problems.append("quality.yml is not callable as a reusable workflow")
    elif "sha" not in (on["workflow_call"].get("inputs") or {}):
        problems.append("quality.yml does not take the commit SHA as an input")

    for job in MANDATORY_JOBS:
        if job not in jobs:
            problems.append(f"quality.yml is missing the mandatory job '{job}'")

    gate = jobs.get("quality-gate")
    if gate is None:
        problems.append("quality.yml has no final quality-gate job")
        return

    gate_needs = gate.get("needs") or []
    for job in MANDATORY_JOBS:
        if job not in gate_needs:
            problems.append(f"quality-gate does not wait for '{job}'")

    # always() is how the gate still reports on a failed prerequisite. It must
    # never be the thing that lets a release through.
    body = yaml.dump(gate)
    if "always()" in str(gate.get("if", "")) and "success" not in body:
        problems.append(
            "quality-gate runs with always() but never checks for 'success' — "
            "a cancelled or skipped prerequisite would pass as approval"
        )

    for job_name, job in jobs.items():
        if job.get("continue-on-error"):
            problems.append(f"job '{job_name}' is continue-on-error, so its failure is invisible")
        if job_name == "quality-gate":
            continue
        steps = yaml.dump(job.get("steps") or [])
        if "inputs.sha" not in steps:
            problems.append(f"job '{job_name}' does not check out the SHA this run is for")
        if "git rev-parse HEAD" not in steps:
            problems.append(f"job '{job_name}' does not assert its checkout is at that SHA")


def check_pr(problems: list[str]) -> None:
    wf = load("pr.yml")
    on = triggers(wf)

    if "pull_request_target" in on:
        problems.append("pr.yml uses pull_request_target, which runs fork code with secrets")
    if "pull_request" not in on:
        problems.append("pr.yml does not run on pull requests")
    elif (on["pull_request"] or {}).get("paths"):
        problems.append("pr.yml filters by path, so mandatory checks can silently not run")

    quality = (wf.get("jobs") or {}).get("quality") or {}
    if "quality.yml" not in str(quality.get("uses", "")):
        problems.append("pr.yml does not call the shared quality workflow")
    if "secrets" in quality:
        problems.append("pr.yml passes secrets to pull-request code")


def check_deploy(problems: list[str]) -> None:
    wf = load("deploy.yml")
    jobs = wf.get("jobs", {})
    on = triggers(wf)

    push = on.get("push") or {}
    if push.get("paths"):
        problems.append("deploy.yml filters the release trigger by path")
    if (wf.get("concurrency") or {}).get("cancel-in-progress"):
        problems.append("a deploy in progress can be cancelled mid-rollout")

    quality = jobs.get("quality") or {}
    if "quality.yml" not in str(quality.get("uses", "")):
        problems.append("deploy.yml does not run the shared quality workflow")
    if str((quality.get("with") or {}).get("sha", "")).strip() != "${{ github.sha }}":
        problems.append("deploy.yml does not check the exact commit it is about to release")

    deploy = jobs.get("deploy") or {}
    if "quality" not in (deploy.get("needs") or []):
        problems.append("the deploy job does not depend on the quality gate")

    steps = yaml.dump(deploy.get("steps") or [])
    # Look for the mechanism, not for wording: read the current tip of main and
    # compare it with the commit this run is for, before anything is shipped.
    if "ls-remote" not in steps or "refs/heads/main" not in steps:
        problems.append(
            "the deploy job never reads the current tip of main, so a superseded "
            "candidate could ship an older tree over a newer one"
        )
    elif "github.sha" not in steps:
        problems.append("the deploy job reads the tip of main but never compares it with this commit")

    guard = yaml.dump(jobs.get("guard") or {})
    if "refs/heads/main" not in guard:
        problems.append("workflow_dispatch is not restricted to main")


def check_canary(problems: list[str]) -> None:
    """The fault switch must stay off the real path, and only ever fail."""
    quality = load("quality.yml")

    for job_name, job in (quality.get("jobs") or {}).items():
        if job_name == "quality-gate":
            continue
        fault = [
            step for step in (job.get("steps") or [])
            if step.get("name") == "Canary fault injection"
        ]
        if not fault:
            problems.append(f"job '{job_name}' has no canary fault step, so the gate cannot be proven to block it")
            continue
        step = fault[0]
        if f"canary_fail == '{job_name}'" not in str(step.get("if", "")):
            problems.append(f"job '{job_name}' canary step is not guarded to its own job name")
        if "exit 1" not in str(step.get("run", "")):
            problems.append(f"job '{job_name}' canary step does not fail, so it proves nothing")

    # The real paths must never be able to inject a fault, and the canary must
    # never be able to reach the server.
    for name in ("pr.yml", "deploy.yml"):
        if "canary_fail" in (WORKFLOWS / name).read_text():
            problems.append(f"{name} references canary_fail; fault injection must stay out of the real path")

    canary_path = WORKFLOWS / "canary.yml"
    if not canary_path.exists():
        problems.append("canary.yml is missing, so the gate graph cannot be exercised safely")
        return
    canary_text = canary_path.read_text()
    for forbidden, why in (
        ("secrets:", "passes secrets"),
        ("ssh ", "runs ssh"),
        ("rsync", "ships code to a server"),
        ("deploy.sh", "invokes the production deploy script"),
    ):
        if forbidden in canary_text:
            problems.append(f"canary.yml {why} — it must not be able to touch production")
    on = triggers(yaml.safe_load(canary_text))
    if set(on) != {"workflow_dispatch"}:
        problems.append(f"canary.yml must be manual only, triggers are {sorted(on)}")


def main() -> int:
    problems: list[str] = []
    check_quality(problems)
    check_pr(problems)
    check_deploy(problems)
    check_canary(problems)

    if problems:
        print("[FAIL] release pipeline wiring")
        for problem in problems:
            print(f"      {problem}")
        return 1

    print("[PASS] release pipeline wiring: one SHA, all mandatory jobs, gate before deploy")
    print("       note: structure only — this does not prove a run behaves this way on GitHub")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
