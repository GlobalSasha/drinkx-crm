---
name: fable5
description: |
  Prompt compiler for the Claude Fable 5 model: takes the user's plain-words
  task prompt (any language, messy numbered fragments welcome) and produces
  ONE engineered English prompt per Anthropic's official "Prompting Claude
  Fable 5" guide — reason-not-only-request context, testable done-criteria,
  explicit boundaries, and only the task-relevant behavioral clauses
  (over-prescription degrades Fable 5). Recon answers what the repo, memory,
  and conversation already know; AskUserQuestion fills only genuinely
  missing pieces. Deliverable: the optimized prompt + one run-now question.
when_to_use: |
  Fires on explicit "/fable5 <raw prompt>" — and auto-fires when a
  substantial build/feature/change request arrives underspecified (goal,
  done-criteria, or scope genuinely open). NOT for trivial edits,
  fully-specified asks, or questions/assessments — handle those directly.
argument-hint: <your raw prompt in plain words>
allowed-tools: Read Glob Grep Bash AskUserQuestion
---

# fable5 — compile a plain-words prompt into a Fable 5 prompt

## Contract

Calling this skill (or having it auto-fire on a messy substantial request)
guarantees:

- The user's raw prompt is fully ingested: every fragment, number, MUST,
  and pasted snippet maps to a line in the produced prompt — nothing
  silently dropped, nothing weakened (user's "MUST" stays MUST).
- Recon happens before any question: repo, memory, and conversation are
  checked first; the user is never asked anything a `Grep` could answer.
- At most ONE AskUserQuestion round (≤4 questions) covering only
  user-only gaps: goal/why, done-criteria, boundaries, taste forks.
- The output is ONE copy-ready prompt in English (regardless of input
  language) built on the seven-part skeleton below, carrying only the
  behavioral clauses relevant to this task type — never the full library.
- The produced prompt never instructs the model to echo, transcribe, or
  explain its internal reasoning (that triggers Fable 5's
  reasoning-extraction refusals).
- Delivery ends with exactly one question: run it now in this session, or
  keep the prompt. Nothing executes before the user answers.

This skill is fat by THFS contract — judgment (what the task really needs,
which clauses fit, what is genuinely missing) lives here in markdown; the
harness stays thin. See `~/.claude/skills/create-skill/reference-thfs.md`.

## Trigger

- "/fable5 <raw prompt>"
- "make this a fable prompt", "optimize this prompt for fable",
  "переведи мой промпт для фейбл"
- Behavioral: a substantial build/feature/change request arrives with
  goal, done-criteria, or scope genuinely open after recon.
- Does NOT fire: trivial edits, fully-specified requests (just do them),
  or the user asking a question / thinking out loud (answer directly).

## Phases

### Phase 1: Ingest and recon

Parse the raw prompt into intent fragments (requirements, constraints,
pasted snippets, references like "as it was before X"). For each fragment,
resolve everything resolvable without the user:

- `Grep`/`Glob`/`Read` the repo for paths, component names, current state,
  exact text of lines the user wants removed or changed.
- `Bash` for live state when referenced (running server, branch, git log
  for "before your last deploy" anchors — resolve to a concrete commit).
- Check session memory and the conversation for project context (what the
  product is, who it's for) to feed the context-why part.

Output (private): a facts list with file:line anchors, plus a gap list of
genuinely user-only unknowns. Target ≤6 recon tool calls; this is a
prompt-compilation pass, not an implementation investigation.

### Phase 2: Gap interview — only if gaps remain

If the gap list is non-empty, ONE `AskUserQuestion` call (≤4 questions),
each question mapped to a named gap: goal/why (who is it for, what does it
enable), done means (a verifiable bar), boundaries (what must not change),
or a genuine taste fork (offer concrete options, first marked
"(Recommended)"). If the gap list is empty, skip straight to Phase 3 —
asking anyway is stalling.

### Phase 3: Compile the prompt

Assemble the English prompt on the seven-part skeleton, in this order:

1. **Context & why** — one short paragraph: "Working on [project] for
   [who]; they need [what the output enables]. With that in mind:"
2. **Task** — numbered requirements, each concrete and testable. Preserve
   the user's own numbering and vocabulary where sound; replace vague
   references with the recon anchors (exact paths, commit hashes, quoted
   line text).
3. **Done means** — acceptance criteria a tool can check: commands to run,
   measurements with thresholds, states to observe (screenshots at named
   viewports, curl codes, build/tsc green).
4. **Boundaries** — what must NOT change, explicit out-of-scope, and for
   code tasks the no-speculative-work clause ("don't add features,
   refactor, or introduce abstractions beyond what the task requires; do
   the simplest thing that works").
5. **Process clauses** — select ONLY rows matching the task from this
   library (deterministic mapping, latent judgment on edge cases):

   | Task signal | Clause to include |
   | --- | --- |
   | Ambiguous / multi-step | act-when-enough-info anti-overplanning clause |
   | Code edits | surgical-changes / no-speculative-abstractions |
   | Long or autonomous run | evidence-grounded progress claims ("audit each claim against a tool result") |
   | Autonomous / destructive-adjacent | checkpoint rule (pause only for destructive, irreversible, scope change, or user-only input) |
   | Long build with a spec | interval self-verification with fresh-context subagents |
   | Headless pipeline | autonomous-operation block (act, don't promise; end-turn check) |
   | UI work | verify against named viewport matrix, not one screenshot |

6. **Reporting** — outcome-first summary clause (complete sentences, no
   working shorthand) when the run is long; omit for small tasks.
7. **Operator footer** — one bracketed meta-line recommending effort
   (high default; xhigh for capability-sensitive work), e.g.
   `[operator: run at effort xhigh]`. This is for the human, not the model.

Hard rules while compiling: English output; brief steering over
enumerations (one short instruction beats listing every behavior); no
"show your thinking/explain your reasoning" language anywhere.

### Phase 4: Deliver and hand off

Print the deliverable per §Output format. Then ONE `AskUserQuestion`:
"Run this prompt now in this session?" — options: Run now / Keep the
prompt only. On "Run now", execute the produced prompt as if the user had
sent it verbatim (it becomes the working brief). On "Keep", stop.

## Quality gates

- Zero questions asked that recon could have answered (each question maps
  to a named gap from Phase 1).
- Full coverage: every fragment of the raw prompt is traceable to a line
  in the produced prompt; user emphasis (MUST/never/all screens) survives
  verbatim in meaning.
- The produced prompt contains parts 1–4 of the skeleton always; parts
  5–7 only when their task signals fire.
- Every "Done means" line names a concrete check (command, measurement,
  viewport, expected state) — no "works well" bars.
- No reasoning-echo instructions in the produced prompt.
- Output prompt is in English even when the input is not.
- Nothing was executed before the user answered the run-now question.

## Anti-Patterns

- ❌ Dumping the full clause library into every prompt — the guide is
  explicit that over-prescription degrades Fable 5 output; clause
  selection IS this skill's judgment.
- ❌ Asking the user for a path, component name, exact line text, or
  "what did it look like before" that `Grep`/`git log` answers.
- ❌ Softening user constraints while rewording ("MUST be 2 lines on all
  screens" becoming "should wrap nicely").
- ❌ Producing a spec, plan, or essay instead of a prompt — the
  deliverable is addressed TO the model, imperative voice, runnable as-is.
- ❌ Writing "explain your reasoning step by step" or "show your
  thinking" into the produced prompt — reasoning-extraction refusal risk
  on Fable 5.
- ❌ Executing the produced prompt without the run-now answer.
- ❌ Inventing acceptance criteria the user never implied instead of
  asking — fabricated done-bars are worse than one question.

## Output format

```
### Optimized Fable 5 prompt

```text
<the compiled prompt, seven-part skeleton, English>
```

**Assumptions made:** <one line per recon-resolved ambiguity, with anchor>
**Left out:** <clauses deliberately not included and why, one line>
```

Then the run-now AskUserQuestion (Run now / Keep the prompt only).

### Worked example (abridged)

Raw input (mixed shorthand): "dev2: 1. all pages markup must be (as it was
before your last deploy to prod) a viewport-locked layout; 2. /home page:
next launch card - name Bosnia & Herzegovina MUST be 2 lines on all types
of screens; 3. /markets/champion - (a) viewport-locked, (b) remove this
line [pasted], (c) top part incl tabs MUST be locked and never scroll, but
the table with coins may scroll inside; (d) tab live MUST be same UX; all
pages same background as /home."

Compiled prompt (shape, not full text):

```text
Context: Sponsio — World Cup 2026 belief-coin market (Next.js 16,
Tailwind v4), dev2 worktree at ~/dev/sponsio-dev2, dev server on
localhost:3001. Restoring the site's signature viewport-locked layout
across all pages before the next prod merge; mid-tournament traffic is
laptops and phones, and scrolling chrome reads as broken. With that in
mind:

Task:
1. Every (site)/ page uses the viewport-locked layout (body never
   scrolls; inner panels scroll) as on main at commit <recon-resolved
   hash>, and shares /home's photo-strip background system.
2. /home next-launch card: "Bosnia & Herzegovina" renders as exactly
   two lines at 390, 768, 1280 and 1440 px widths.
3. /markets/champion, both Upcoming and Live tabs: header, market nav,
   stat strip and status tabs stay fixed; only the coin table scrolls,
   inside the locked viewport.
4. Remove the line "<exact text from recon>" at <file:line>.

Done means: body scrollHeight equals clientHeight on every page at
1440×900 and 390×844 while the board panel scrolls internally;
screenshots at 1280×727, 1366×768, 1440×900, 390×844 show full chrome,
the two-line name, and tabs fixed with the table scrolled past row 20;
tsc and production build green.

Boundaries: don't touch main/prod, tokens.json, /mini, or reward copy.
Don't add features, refactor, or introduce abstractions beyond what the
task requires; do the simplest thing that works.

Process: when you have enough information to act, act. Verify against
the checks above before claiming done; report outcome first with
evidence.

[operator: run at effort xhigh]
```
