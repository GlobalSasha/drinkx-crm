# Plan 022: Protect untracked PII + local tooling state from accidental commit

> **Executor instructions**: Follow step by step. Run every verification
> command. Honor STOP conditions. Update this plan's row in `plans/README.md`
> when done.
>
> **Drift check (run first)**: `git status --porcelain | grep -E "lpr_import|\.beads|\.codex|CRM_AUDIT"`
> and `git check-ignore scripts/lpr_import/parsed_leads.json` (expected: no
> output today — that is the bug). If `scripts/lpr_import/` no longer exists or
> is already ignored, re-scope or STOP.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security + dx
- **Planned at**: commit `493a962`, 2026-07-18

## Why this matters

`scripts/lpr_import/parsed_leads.json` (~110 KB, plus an identical
`parsed_leads 2.json`) contains **real third-party PII** — decision-maker
names, titles, phones, emails, and office addresses for named Russian retail
companies. These files are untracked AND matched by no `.gitignore` rule
(verified: `git check-ignore` returns nothing). A single routine `git add -A`
would commit contact-level PII into git history — irreversible even after later
deletion, and a data-protection problem for those individuals. The same
unguarded state applies to local agent/tooling dirs (`.beads/` with a 324 KB
embedded DB, `.codex/`, downloaded skills) whose noise in `git status` also
raises the odds of an accidental bulk commit. This is pure prevention — it
changes nothing at runtime.

## Current state

- `.gitignore` (repo root) — read in full; it covers OS/editor/node/python/env
  artifacts but **none** of: `scripts/lpr_import/`, `.beads/`, `.codex/`,
  `.agents/skills/`, `.claude/skills/`, `CRM_AUDIT_REPORT.md`.
- `scripts/lpr_import/` contents (all untracked):
  - `parse_cards.py` + duplicate `parse_cards 2.py` — a pure stdlib offline
    parser (no secrets, no network, no SQL; its docstring states it writes
    nothing to a DB). This SOURCE is safe to keep/track if desired.
  - `parsed_leads.json` + duplicate `parsed_leads 2.json` — the GENERATED PII
    output. Must never be committed.
- `.claude/launch.json` IS legitimately tracked, so ignore `.claude/skills/`
  specifically, not all of `.claude/`.
- Note: `git status` at session start showed `M .claude/launch.json` and
  `M skills-lock.json` already tracked — do not add those to ignore.

## Commands you will need

| Purpose            | Command                                                        | Expected on success |
|--------------------|----------------------------------------------------------------|---------------------|
| Verify PII ignored | `git check-ignore scripts/lpr_import/parsed_leads.json`        | prints the path     |
| Verify tooling ignored | `git check-ignore .beads/ .codex/`                        | prints both paths   |
| Verify launch still tracked | `git check-ignore .claude/launch.json`               | **no output** (not ignored) |
| Nothing staged     | `git diff --cached --name-only`                                | empty               |

## Scope

**In scope**:
- `.gitignore` (repo root) — add ignore rules

**Out of scope** — do NOT do these without an explicit follow-up decision:
- Deleting the untracked files from disk (they're the user's local data;
  ignoring is enough to prevent the leak). You MAY delete the ` 2.`-suffixed
  duplicate junk copies (`parse_cards 2.py`, `parsed_leads 2.json`) since those
  are accidental dupes — but confirm they are byte-identical first.
- Rewriting git history (nothing is committed yet — not needed).
- Moving `CRM_AUDIT_REPORT.md` into `docs/` — that's a separate editorial call.
- Any source code.

## Git workflow

- Branch: `advisor/022-gitignore-hygiene`
- Commit style: `chore: gitignore local PII import output and agent tooling state`
- Do NOT push unless the operator asks.

## Steps

### Step 1: Add ignore rules

Append to `.gitignore`:
```gitignore
# Local LPR import artifacts — generated PII output, must never be committed
scripts/lpr_import/

# Local agent / tooling state (not part of the app)
.beads/
.codex/
.agents/skills/
.claude/skills/
CRM_AUDIT_REPORT.md
```
Rationale for `.claude/skills/` (not `.claude/`): `.claude/launch.json` is
tracked and must stay tracked.

**Verify**:
- `git check-ignore scripts/lpr_import/parsed_leads.json` → prints the path
- `git check-ignore .beads/ .codex/ .agents/skills/ .claude/skills/ CRM_AUDIT_REPORT.md` → prints all
- `git check-ignore .claude/launch.json` → **no output** (still tracked)
- `git status --porcelain` → the `??` lines for those paths are gone

### Step 2 (optional): remove byte-identical ` 2.` duplicates

Only if Step 1 verified clean AND the files are byte-identical:
```
cmp scripts/lpr_import/parse_cards.py "scripts/lpr_import/parse_cards 2.py"
cmp scripts/lpr_import/parsed_leads.json "scripts/lpr_import/parsed_leads 2.json"
```
If both `cmp` report no difference, delete the ` 2.` copies. If they differ,
leave them and report.

**Verify**: `ls scripts/lpr_import/` shows no ` 2.` files (if you removed them).

## Test plan

No code tests — this is ignore-rule hygiene. The `git check-ignore` probes in
"Commands you will need" ARE the verification.

## Done criteria

- [ ] `git check-ignore scripts/lpr_import/parsed_leads.json` prints the path
- [ ] `git check-ignore .beads/ .codex/ CRM_AUDIT_REPORT.md` prints all three
- [ ] `git check-ignore .claude/launch.json` prints nothing (still tracked)
- [ ] `git status --porcelain` no longer lists the PII/tooling paths as `??`
- [ ] No source files modified; only `.gitignore` (and optionally deleted ` 2.` dupes)
- [ ] `plans/README.md` status row updated

## STOP conditions

- `git check-ignore .claude/launch.json` prints a path (means you over-ignored
  `.claude/` and would drop a tracked file) — fix the rule to `.claude/skills/`.
- Any of the target files turns out to be already git-tracked
  (`git ls-files <path>` returns it) — then ignoring won't help; STOP and
  report (it needs `git rm --cached` + a history discussion, out of scope here).

## Maintenance notes

- If the LPR import is ever productionized, track `parse_cards.py` under a
  documented `scripts/` path and keep the `parsed_leads*.json` outputs ignored.
- Reviewer should confirm no real data file is being ADDED in the same PR.
- Consider a pre-commit hook that blocks committing files matching
  `parsed_leads*.json` as a second layer of defense.
