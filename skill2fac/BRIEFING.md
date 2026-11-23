# skill2fac: briefing for a meeting with my professor

> **How to use this file:** read it straight through, or paste it into a chat LLM with a prompt like
> *"Restate this for me in plain language, then quiz me on it as if you were my professor."*
> Everything here comes from the code and results in the `skill2fac/` folder (as of 2026-11-23).

---

## 1. The one-sentence pitch

**skill2fac automatically turns an AI "agent skill" (a single big prompt file, `SKILL.md`) into a multi-step fac workflow (`fac.yaml`), then runs both versions on real inputs to test whether splitting the work into steps gives better results, and what that costs.**

## 2. Background you need first

### What is fac?
- fac is a **make-like build system for LLM projects** (it lives in this repo, `fac/` and `facd/`).
- A `fac.yaml` file plays the role of a Makefile. It lists **targets**, and each target is **one file**.
- Each file is built by either:
  - **one LLM call:** the target has a `description` (the prompt), and the model's reply becomes the file; or
  - **one shell command:** the target has a `cmd`, usually `jq`, `cat` or a `for` loop that stitches files together.
- Targets declare **dependencies**. A dependency sets the build order, and its contents can be pasted into the prompt (`include: true`).
- **Fan-out:** a path like `tickets/$N.md` plus a shell command that lists values for `$N` makes fac build one file per value (one LLM call per ticket, for example).
- fac works inside a git repo and auto-commits builds. There is also a daemon, `facd`, with a web UI, but skill2fac does not use it.

### What is an "agent skill"?
- A `SKILL.md` is a markdown instruction file for an AI agent (in the style of Claude Code skills). It tells the agent how to do a job: "write a spec", "break this into tickets", "threat-model this system", and so on.
- Normally the whole skill runs as **one long prompt** in **one conversation**. The agent may also ask the user questions, wait for approval and use tools.

### The research question
> If you break a skill into explicit, separate LLM steps (a fac workflow), is the final output **better**, and is the improvement **worth the extra cost**?

## 3. What I built (the pipeline)

The folder is **standalone**: it does not import fac's Python code. It only calls the `fac` command-line tool.

```
SKILL.md ──convert.py──► fac.yaml ──evaluate.py──► baseline output  vs  fac output ──► compare.md + summary.md
```

### Files at a glance

| File | What it does |
|---|---|
| `convert.py` | Converts one skill into a `fac.yaml` using one structured LLM call, with validation and retries. |
| `converter_prompt.md` | System prompt that teaches the converter LLM how fac works, plus 2 worked examples. |
| `converter_schema.json` | JSON schema that the converter's answer must follow. It forces a 4-step reasoning order. |
| `evaluate.py` | Runs each sample input 2 ways (baseline and fac) and writes side-by-side reports. |
| `common.py` | Shared helpers: paths, skill loading, the OpenRouter API call, git repo setup. |
| `test_convert.py` | Offline unit tests (no API calls) for the conversion and validation logic. |
| `skills/` | The 4 vendored skills, each pinned to a source commit. |
| `inputs/` | 8 real-world sample inputs (2 per skill), each with its source URL at the top. |
| `runs/` | All outputs: generated workflows, per-input results, `summary.md`, `comparison.md`. |
| `Dockerfile` | Linux environment (fac needs bash and jq), so it runs on my Windows machine. |

### Step A: conversion (`convert.py`)

1. It sends **one structured-output LLM call**. The schema makes the model work in this order:
   1. **Classify** every instruction in the skill into one of 5 categories:
      - **operation:** real work that produces information, so it becomes a target;
      - **constraint:** a rule the output must follow, so it is copied **word for word** into each target it governs;
      - **style:** tone or format guidance, so it is copied into each target that writes prose for the reader;
      - **approval:** "ask the user", "wait for approval". These are **dropped**, because the workflow runs unattended. The model is told to state its assumptions instead;
      - **control:** sequencing, loops, if/then logic, realized as dependencies, fan-out or shell commands.
   2. **Plan the artifacts** (the intermediate files).
   3. **Pick the final target** (one concrete file that holds the deliverable).
   4. **Write the targets** (prompts, commands, schemas, dependencies, variables).
2. Python turns that JSON into `fac.yaml`. It:
   - adds a `model:` to every LLM target;
   - marks `input.md` as user-supplied (`in_fac.yaml: false`);
   - **escapes `$`, backticks and backslashes**, because fac pastes descriptions into a bash heredoc, where those characters would be interpreted by the shell. References to the target's own variables (like `$TICKET_ID`) are kept.
3. **Validation**, with up to 3 attempts. Errors are fed back to the model so it can fix them:
   - the JSON schema check;
   - graph checks: every dependency resolves, `input.md` is used, there are no cycles, the final target is concrete, `$VARIABLES` are declared, no `$(...)` in prompts;
   - a real **`fac --dryrun`** in a throwaway git repo.

**Key design rule given to the converter:** each LLM call in fac is isolated, cannot see the skill, has no tools and cannot ask questions. So every prompt must be **self-contained**, and the templates and constraints must be copied into it.

### Step B: evaluation (`evaluate.py`)

For each input it runs:
- **Baseline:** 1 LLM call. The system prompt is `SKILL.md` (plus a short preamble) and the user message is the input.
- **fac:** a fresh git repo containing `fac.yaml` and the input saved as `input.md`, built with `fac <final_target>`.

**Fairness:** both sides get the same model and the same non-interactive rules: no user to ask, no tools, state your assumptions, reply with only the deliverable.

**Outputs per input:** `baseline.md`, the `fac/` project with all intermediate files, `fac.log`, `metrics.json` (time, cost, number of calls, words) and `compare.md` (both outputs side by side). There is also a summary table in `runs/summary.md`.

## 4. The 4 skills and what fac turned each into

| Skill | What it does | Generated fac pipeline |
|---|---|---|
| **to-spec** | Turns a feature discussion into a product spec (user stories, decisions, testing). | `seams.md` → `user_stories.md` → `spec.md` (3 calls) |
| **to-tickets** | Turns a spec into "tracer-bullet" tickets (thin end-to-end slices first). | `slices.json` → `review.md` → `tickets.json` → one call per ticket `tickets/$N.md` → shell join into `tickets.md` (12–14 calls) |
| **doc-coauthoring** | Co-writes a document for a target reader. | context → structure → one call per section → draft → reader questions → reader test → review → final `doc.md` (about 10 calls) |
| **security-threat-model** | Writes a threat model for a codebase or architecture. | 5 analysis stages (repo summary, system model, assets/attackers, threats, assumptions) → draft → review → final `threat-model.md` (8 calls) |

**Inputs (all real, 2 per skill):** an httpx Server-Sent-Events issue, an fd "multiple patterns" issue, Sentry escalating-issues, PEP 723, Node.js TSC meeting minutes, an fzf headless-mode proposal, the **facd daemon itself** (this repo), and the Immich architecture.

## 5. Results (the part the professor will care about most)

Full write-up: `runs/comparison.md`.

### Headline findings
1. **fac wins when the skill asks for analysis in stages.** Both threat models were clearly more accurate with fac. The to-tickets review step also produced better slices on the Sentry input.
2. **The baseline wins when the reader needs something short.** For the meeting summary, fac's output was 2.3x longer and full of caveats. It missed the stated goal of being readable in under 3 minutes (about 6.5 minutes vs about 3).
3. **fac always costs more: 3.3x to 10.1x the total characters** (prompts plus replies). The cost grows with pipeline depth, because **every stage re-reads the input and the upstream files**. Output words were only 1.1–2.3x more, so most of the extra cost is re-read input, not more output.
4. **fac crashed on 1 of 8 inputs** because of a bug in fac (see below). The baseline never failed.
5. **The converter worked on the first attempt for all 4 skills.** Every `fac.yaml` passed the schema check, the graph checks and a real `fac --dryrun`, and the designs were sensible (parallel analyses, fan-out, critique → revise loops).

### Tally across the 8 inputs
- fac: 3 clear wins and 1 slight win. Baseline: 2 clear wins (one is the crash) and 1 slight win. 1 tie.
- Scoring a clear win as 1 and a slight win as 0.5: **fac 3.5, baseline 2.5.** fac leads, but not decisively. **The pattern of which skills fac wins is more useful than the score.**

| Skill / input | fac calls | Cost multiple | Verdict |
|---|---|---|---|
| to-spec / httpx SSE | 3 | 3.3x | Tie |
| to-spec / fd | 3 | 3.7x | fac, slightly |
| to-tickets / Sentry | 12 | 4.8x | **fac** |
| to-tickets / PEP 723 | 14 | 5.6x | baseline, slightly |
| doc-coauthoring / Node.js minutes | 10 | 8.5x | **baseline** |
| doc-coauthoring / fzf | 2 (crashed) | — | **baseline** (fac failed) |
| threat-model / Immich | 8 | 10.1x | **fac** |
| threat-model / facd | 8 | 10.1x | **fac** |

### Good concrete examples to cite
- **facd threat model (ground truth available, since it is our own code):**
  - fac found that `git checkout .` or `git checkout fac.yaml` (a path-form ref) silently discards uncommitted work **without** a force flag. The baseline missed this.
  - The baseline made a **factual error**. Its threat TM-008 assumes that cloning copies `.git/hooks` or `.git/config`, which clones do not do. fac stated that correctly.
- **Sentry tickets:** fac's separate review stage split an oversized forecast ticket, so a user could demo archive → escalate earlier.
- **PEP 723 tickets:** the baseline's ticket 01 was a true end-to-end tracer bullet. fac's first end-to-end run did not come until ticket 06, and fac added out-of-scope tickets (a cache and a trust notice).
- **to-spec:** fac made 2–3x more user stories (92 vs 50, and 75 vs 25), but some were padding or off-topic. On httpx, fac's own "out of scope" section contradicted one of its stories.

### Cross-cutting lessons (good discussion material)
1. **One job per stage → more items.** A focused stage produces 2–3x more items than one call that does everything. Sometimes that means better coverage, sometimes padding.
2. **Review → revise loops are fac's best feature and its main risk.** They improved accuracy, but each review **adds caveats and nothing removes them**, so documents grow. Fix: copy length and brevity constraints word for word into every revise target.
3. **Parallel fan-out calls don't agree on format.** Each ticket call picked its own numbering (`0003`, `03` or `3`). Fix: state shared conventions in the prompt, or normalize them in the shell join step.
4. **The fac bug that caused the crash:** fac asserts that variable values contain no `$` (`fac/BuildContext.py:256`). The doc-coauthoring workflow fanned out over free-text fields, the model quoted `$SHELL=BASH` from the source thread, and fac raised an `AssertionError`. Fix: fan out over **IDs only**, and have each target read its item's text from the JSON.
5. **The converter can drop parts of the output contract.** Both threat models lost the required "assumption check-in" and "Notes on use" sections, because the converter left them out of the final target's section list.

## 6. Limitations (be upfront about these)

- **1 run per side per input.** LLM output varies between runs, so "slight" verdicts could flip.
- **1 judge, not blind.** The judging was done with an LLM (Opus) that knew which output was which, so it may favor longer or more structured outputs.
- **The model that actually answered differs from the one the files name.** The scripts default to `deepseek/deepseek-v4.1-flash` via OpenRouter, but for these runs every call went through a local relay to **Sonnet 5.5 subagents**. `metrics.json` shows the requested model id, not the one that replied.
- **No real dollar cost or timing.** The relay costs $0, so the cost column in `summary.md` is $0.0000. Character count is used as the cost proxy instead. Wall-clock seconds reflect relay latency and cache hits, not model speed (one baseline took 2.1 s because of a cache hit).
- **No interaction.** The skills expect a user to answer questions and approve steps, and both sides had that removed. This hurts doc-coauthoring most, because interaction is the core of that skill.
- **No codebase access.** to-spec and to-tickets normally explore a repo. Here they only had issue text, so prefactor tickets are guesses on both sides.
- **Small sample:** 4 skills × 2 inputs.

## 7. Evaluation method I designed (for future runs)

`runs/comparison.md` defines a reusable rubric so later runs can be compared with these:
- **Score only the deliverable** (the final file the user reads). Intermediate files may explain a difference but are not scored.
- **7 criteria.** Two are gates: (1) **Completion** and (2) **Accuracy**. Then (3) Contract, i.e. does it follow the skill's required format; (4) Coverage; (5) Precision; (6) Core task, from a per-skill rubric; (7) Cost.
- **Fairness rules:** hide which method produced which output, count instead of using adjectives, quote evidence, don't reward length (unless the skill asks for it), find the cause of each defect (fac tool / converter / harness / model), run each side 3+ times, and use ground truth where it exists.
- **Decision order:** gates → core task → coverage, precision and contract → cost last. An accuracy gain can be worth 10x the cost; a higher item count alone isn't worth 3x.

## 8. Next steps

1. Add the fixes from the lessons above to `converter_prompt.md`: carry brevity constraints into revise steps, fan out over IDs only, normalize numbering in the join step, and list every required section in the final target.
2. Re-convert and rerun only the affected inputs (the relay cache replays unchanged calls for free).
3. Add automatic checks to `evaluate.py`: completion, required sections, item counts, numbering and word counts.
4. Run each side 3 times and score blind with the rubric.
5. Check every facd threat against the actual source code to get a ground-truth accuracy score.
6. Possibly fix or report the `$` assertion in fac itself.

## 9. Questions the professor might ask (with short answers)

- **Why not just write the fac.yaml by hand?** The goal is to see whether a skill can be converted *automatically*. The converter worked on the first try for all 4 skills, which suggests it can.
- **Is fac better?** It depends on the task. It is better for staged analysis where accuracy matters (threat models), and worse for short reader-facing documents. It is always 3–10x more expensive.
- **Why is fac so much more expensive?** Each stage re-reads `input.md` and the upstream files, so the cost multiplies with graph depth. Output length only rose 1.1–2.3x.
- **How do you know the comparison is fair?** Both sides get the same model and the same non-interactive rules, and both start from the same skill text. Weak points: 1 run each and a non-blind judge (these are listed as limitations, with a plan to fix them).
- **What's the most interesting result?** On the facd threat model, where we have ground truth, the staged version caught a real data-loss issue the baseline missed, and avoided a factual error the baseline made.
- **What broke?** One crash caused by a fac bug (`$` in a variable value), plus converter omissions (missing required sections) and inconsistent numbering across parallel calls. Each has a known fix.
- **How do you run it?**
  - Build the Docker image from the repo root: `docker build -f skill2fac/Dockerfile -t fac-skill2fac .`
  - Inside the container: `python3 convert.py to-tickets`, then `python3 evaluate.py --skill to-tickets` (or just `python3 evaluate.py` for everything).
  - Tests: `pytest test_convert.py`.
  - It needs `OPENROUTER_API_KEY` in the repo's `.env`.

## 10. Small things to know so I'm not caught off guard

- The README says `evaluate.py --skill to-spec` runs "all 3 inputs", but each skill has only **2** inputs. It's a stale line.
- `skill2fac/` is **not committed to git yet** (it shows as untracked).
- The threat-model skill includes an extra reference file (`references/prompt-template.md`), because it defines that skill's output format.
- `common.init_repo` writes `.fac.log` into `.gitignore`. This fixes a harness bug: fac creates its log file at startup, which made the fresh repo "dirty", and fac refuses to run in a dirty repo.
