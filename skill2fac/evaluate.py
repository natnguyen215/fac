"""
Compare a skill with its fac version on the sample inputs.

For each input, run (a) the original skill as one LLM call and (b) the converted
fac workflow, then write both outputs into a markdown file for manual review.

    python evaluate.py                                  # all skills, all inputs
    python evaluate.py --skill to-tickets
    python evaluate.py --input inputs/to-spec/1-httpx-server-sent-events.md
    python evaluate.py --skill to-spec --reconvert      # regenerate fac.yaml first

Writes runs/<skill>/<input>/{baseline.md, fac/, fac.log, metrics.json, compare.md}
and runs/summary.md.
"""

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

from common import (
    DEFAULT_MODEL, INPUT_FILE, INPUTS_DIR, RUNS_DIR,
    chat, init_repo, list_skills, load_skill, read_text, write_text,
)
from convert import convert, dump_yaml, to_fac_config

# The skills are written for interactive agents with tools. The baseline gets the
# same ground rules that converter_prompt.md gives every fac target.
BASELINE_PREAMBLE = """\
You are running the skill below non-interactively, as a single response.
- There is no user to answer questions or approve steps. Wherever the skill says to ask, quiz,
  check with, or wait for the user, make reasonable assumptions, state them explicitly, and continue.
- You have no tools: you cannot explore a repository, fetch URLs, run code, or publish to a tracker.
  Work only from the material in the user's message, and produce the content those actions would have produced.
- Reply with only the final deliverable, in the format the skill specifies.

<skill>
{skill}
</skill>
"""


# ---------------------------------------------------------------------------
# The two sides of the comparison
# ---------------------------------------------------------------------------

def run_baseline(skill, input_text, model, out_dir):
    """The original skill: one LLM call, skill as system prompt, input as user message."""
    messages = [
        {"role": "system", "content": BASELINE_PREAMBLE.format(skill=load_skill(skill))},
        {"role": "user", "content": input_text},
    ]
    text, info = chat(messages, model)
    write_text(out_dir / "baseline.md", text)

    return {"seconds": info["seconds"], "cost": info["cost"], "calls": 1, "words": len(text.split())}


def run_fac(spec, input_text, model, out_dir):
    """The fac version: a fresh git repo with fac.yaml + input.md, built with `fac <final_target>`."""
    project = out_dir / "fac"
    if project.exists():
        shutil.rmtree(project)
    project.mkdir(parents=True)

    write_text(project / "fac.yaml", dump_yaml(to_fac_config(spec, model)))
    write_text(project / INPUT_FILE, input_text)
    init_repo(project)

    start = time.time()
    result = subprocess.run(["fac", spec["final_target"]], cwd=project, capture_output=True, text=True)
    seconds = round(time.time() - start, 1)
    write_text(out_dir / "fac.log", result.stdout + result.stderr)

    # fac can exit 0 even when a build failed, so success = the final file exists.
    final_file = project / spec["final_target"]
    text = read_text(final_file) if final_file.exists() else ""

    builds = read_buildlog(project)
    llm_builds = [b for b in builds if "cost" in b]  # shell (cmd) builds have no cost
    return {
        "seconds": seconds,
        "cost": sum(b["cost"] for b in llm_builds),
        "calls": len(llm_builds),
        "words": len(text.split()),
        "ok": final_file.exists(),
        "exit_code": result.returncode,
    }


def read_buildlog(project):
    """fac appends one JSON line per built file to .buildlog."""
    buildlog = project / ".buildlog"
    if not buildlog.exists():
        return []
    lines = read_text(buildlog).splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def intermediate_files(project, final_target):
    """Files fac built besides the final target (skips fac.yaml, input.md and dotfiles)."""
    skip = {"fac.yaml", INPUT_FILE, final_target}
    files = []
    for path in project.rglob("*"):
        relative = path.relative_to(project)
        is_hidden = any(part.startswith(".") for part in relative.parts)
        if path.is_file() and not is_hidden and relative.as_posix() not in skip:
            files.append(relative.as_posix())
    return sorted(files)


def fmt_cost(cost):
    return "?" if cost is None else f"${cost:.4f}"


def write_compare(skill, input_path, spec, metrics, out_dir):
    baseline, fac = metrics["baseline"], metrics["fac"]
    final = spec["final_target"]
    source_line = read_text(input_path).splitlines()[0]  # "<!-- source: ... -->"

    if fac["ok"]:
        fac_output = read_text(out_dir / "fac" / final)
    else:
        fac_output = f"*fac did not produce `{final}` (exit code {fac['exit_code']}); see [fac.log](fac.log).*"

    links = [f"[{f}](fac/{f})" for f in intermediate_files(out_dir / "fac", final)]

    report = f"""\
# {skill} / {input_path.stem}

Input: [{input_path.name}](../../../inputs/{skill}/{input_path.name}) {source_line}
Model: `{metrics['model']}`

| | baseline (1 call) | fac |
|---|---|---|
| wall time (s) | {baseline['seconds']} | {fac['seconds']} |
| cost | {fmt_cost(baseline['cost'])} | {fmt_cost(fac['cost'])} |
| LLM calls | {baseline['calls']} | {fac['calls']} |
| output words | {baseline['words']} | {fac['words']} |

fac intermediate artifacts: {', '.join(links) or 'none'}

---

# Baseline output

{read_text(out_dir / 'baseline.md')}

---

# fac output (`{final}`)

{fac_output}
"""
    write_text(out_dir / "compare.md", report)


def write_summary():
    """One table row per run found under runs/ (pairs are baseline / fac)."""
    lines = [
        "# skill2fac summary",
        "",
        "Pairs are baseline / fac.",
        "",
        "| skill | input | seconds | cost | fac calls | words | fac ok | |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for metrics_file in sorted(RUNS_DIR.glob("*/*/metrics.json")):
        m = json.loads(read_text(metrics_file))
        b, f = m["baseline"], m["fac"]
        link = f"[compare]({metrics_file.parent.relative_to(RUNS_DIR).as_posix()}/compare.md)"
        ok = "yes" if f["ok"] else "**no**"
        lines.append(
            f"| {m['skill']} | {m['input']} | {b['seconds']} / {f['seconds']} "
            f"| {fmt_cost(b['cost'])} / {fmt_cost(f['cost'])} | {f['calls']} "
            f"| {b['words']} / {f['words']} | {ok} | {link} |"
        )
    write_text(RUNS_DIR / "summary.md", "\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def evaluate(skill, input_path, model):
    """Run both sides on one input and write metrics.json + compare.md."""
    spec = json.loads(read_text(RUNS_DIR / skill / "fac.json"))
    out_dir = RUNS_DIR / skill / input_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    input_text = read_text(input_path)
    name = f"{skill}/{input_path.stem}"

    print(f"[{name}] baseline...")
    baseline = run_baseline(skill, input_text, model, out_dir)

    print(f"[{name}] fac {spec['final_target']}...")
    fac = run_fac(spec, input_text, model, out_dir)

    metrics = {"skill": skill, "input": input_path.stem, "model": model, "baseline": baseline, "fac": fac}
    write_text(out_dir / "metrics.json", json.dumps(metrics, indent=2))
    write_compare(skill, input_path, spec, metrics, out_dir)
    print(f"[{name}] -> {out_dir / 'compare.md'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skill", action="append", help=f"repeatable; default: all of {', '.join(list_skills())}")
    parser.add_argument("--input", type=Path, help="a single input file under inputs/<skill>/")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--reconvert", action="store_true", help="regenerate fac.yaml even if it exists")
    args = parser.parse_args()

    # Build the list of (skill, input file) pairs to run.
    if args.input:
        input_path = args.input.resolve()
        jobs = [(input_path.parent.name, input_path)]
    else:
        skills = args.skill or list_skills()
        jobs = [(skill, path) for skill in skills for path in sorted((INPUTS_DIR / skill).glob("*.md"))]

    # Convert each skill once, if needed, before evaluating.
    for skill in sorted({skill for skill, _ in jobs}):
        if args.reconvert or not (RUNS_DIR / skill / "fac.yaml").exists():
            convert(skill, args.model)

    for skill, input_path in jobs:
        evaluate(skill, input_path, args.model)

    write_summary()
    print(f"summary: {RUNS_DIR / 'summary.md'}")


if __name__ == "__main__":
    main()
