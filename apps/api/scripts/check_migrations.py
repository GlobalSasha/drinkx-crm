#!/usr/bin/env python3
"""Run the real Alembic chain against a disposable PostgreSQL database.

The API test fixtures build their schema with `Base.metadata.create_all`, which
never executes a single migration. Production boots with `alembic upgrade head`.
Those are two different code paths, and only one of them was covered — a broken
migration could pass CI and then fail on deploy.

This check closes that gap:

  1. refuse to run against anything but a throwaway database;
  2. `alembic upgrade head` on a clean database — the real chain, no create_all;
  3. exactly one head, taken from Alembic itself rather than from any document;
  4. the database's current revision equals that head;
  5. a second `upgrade head` succeeds, re-applies no revision AND performs no
     bootstrap DDL of its own. The absence of "Running upgrade" alone would
     only show that no revision file ran again; the env bootstrap used to emit
     CREATE and ALTER on every invocation regardless (review finding R3).

Not covered here, on purpose: migrating an existing database from an older
revision and checking data survives. That belongs with a pull request that
actually changes the chain, against that pull request's base revision — not an
arbitrary old revision picked to look thorough.

Usage (from apps/api, with DATABASE_URL pointing at a disposable database):

    python scripts/check_migrations.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from scripts.db_safety import UnsafeDatabaseTarget, assert_disposable, redact  # noqa: E402

REVISION_RE = re.compile(r"^([0-9a-zA-Z_]+)")


def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )


def die(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def show(step: str, proc: subprocess.CompletedProcess[str]) -> None:
    print(f"--- {step} (exit {proc.returncode}) ---")
    for stream in (proc.stdout, proc.stderr):
        text = (stream or "").strip()
        if text:
            print(text)


def main() -> int:
    dsn = os.environ.get("DATABASE_URL", "")
    try:
        assert_disposable(dsn, purpose="Alembic migration check")
    except UnsafeDatabaseTarget as exc:
        die(str(exc))

    print(f"migration target: {redact(dsn)}")

    # 1. The real chain on a clean database.
    first = run_alembic("upgrade", "head")
    show("alembic upgrade head (first run)", first)
    if first.returncode != 0:
        die("the migration chain does not apply to a clean database")

    applied = [
        line for line in (first.stdout + first.stderr).splitlines()
        if "Running upgrade" in line
    ]
    if not applied:
        die("the first upgrade applied no migrations — the database was not clean")
    print(f"migrations applied: {len(applied)}")

    # 2. Exactly one head, asked of Alembic rather than read from a document.
    heads_proc = run_alembic("heads")
    show("alembic heads", heads_proc)
    if heads_proc.returncode != 0:
        die("could not read the head revision")
    heads = [
        m.group(1)
        for line in heads_proc.stdout.splitlines()
        if (m := REVISION_RE.match(line.strip()))
    ]
    if len(heads) != 1:
        die(f"expected exactly one head, found {len(heads)}: {heads} — the chain has branched")
    head = heads[0]
    print(f"single head: {head}")

    # 3. The database is actually at that head.
    current_proc = run_alembic("current")
    show("alembic current", current_proc)
    if current_proc.returncode != 0:
        die("could not read the current revision")
    current = [
        m.group(1)
        for line in current_proc.stdout.splitlines()
        if (m := REVISION_RE.match(line.strip()))
    ]
    if current != [head]:
        die(f"database is at {current}, expected [{head}]")

    # 4. Re-running must be a no-op, not a second application.
    second = run_alembic("upgrade", "head")
    show("alembic upgrade head (second run)", second)
    if second.returncode != 0:
        die("re-running upgrade head failed — migrations are not idempotent")
    second_output = second.stdout + second.stderr
    reapplied = [line for line in second_output.splitlines() if "Running upgrade" in line]
    if reapplied:
        die(f"the second upgrade re-applied {len(reapplied)} migration(s): {reapplied}")

    # The env bootstrap announces itself when it creates or widens the version
    # table. On an already-correct database it must stay silent, because it
    # must not run any DDL at all.
    bootstrapped = [line for line in second_output.splitlines() if line.startswith("alembic: ")]
    if bootstrapped:
        die(f"the second run still performed bootstrap DDL: {bootstrapped}")

    print()
    print(f"OK: chain applies cleanly to head {head}; one head; the second run")
    print("    re-applied no revision and issued no bootstrap DDL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
