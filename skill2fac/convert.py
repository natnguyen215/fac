"""
Convert an agent skill (SKILL.md) into a fac.yaml.

One structured-output LLM call produces the workflow as JSON. Python checks it,
feeds any problems back to the model (up to --attempts times), and writes YAML.

    python convert.py to-spec
    python convert.py --all

Writes runs/<skill>/fac.json, fac.yaml, and convert_log.json.
"""

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import jsonschema
import yaml

from common import (
    DEFAULT_MODEL, HERE, INPUT_FILE, RUNS_DIR,
    chat, init_repo, list_skills, load_skill, read_text, write_text,
)

SCHEMA = json.loads(read_text(HERE / "converter_schema.json"))
SYSTEM_PROMPT = read_text(HERE / "converter_prompt.md")

# Matches a shell variable reference: $NAME or ${NAME}. Group 1 is the name.
VAR_REF = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")

# Matches a variable reference, or a lone backslash, backtick, or dollar sign.
SHELL_SPECIAL = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?|[\\`$]")


# ---------------------------------------------------------------------------
# JSON -> fac.yaml
# ---------------------------------------------------------------------------

def escape_description(text, variables):
    """
    Make a description safe for fac's bash templating.

    fac pastes `description` into an unquoted bash heredoc (fac/util/templates.py),
    so backslashes, backticks and `$` would be interpreted by bash. We escape all
    of them, except references to the target's own variables (e.g. $TICKET_ID),
    which fac is supposed to fill in.
    """
    def escape(match):
        is_own_variable = match.group(1) in variables
        if is_own_variable:
            return match.group(0)
        return "\\" + match.group(0)

    return SHELL_SPECIAL.sub(escape, text)


def to_fac_config(spec, model):
    """Turn the converter's JSON into a fac.yaml dict (target path -> target settings)."""
    config = {}

    for target in spec["targets"]:
        variables = {v["name"]: v["command"] for v in target["variables"]}
        entry = {}

        if target["cmd"]:
            entry["cmd"] = target["cmd"]
        else:
            entry["description"] = escape_description(target["description"], variables)
            # fac reads the model for text targets from the top-level `model` key.
            entry["model"] = f"openrouter/{model}"

        if target["schema"]:
            entry["schema"] = target["schema"]

        dependencies = [to_fac_dependency(dep) for dep in target["dependencies"]]
        if dependencies:
            entry["dependencies"] = dependencies

        if variables:
            entry["variables"] = variables

        config[target["path"]] = entry

    return config


def to_fac_dependency(dep):
    """A plain path string when possible, otherwise a dict with the extra options."""
    result = {"target": dep["target"]}
    if dep["target"] == INPUT_FILE:
        # input.md is supplied by the user, not built by fac.
        result["in_fac.yaml"] = False
    if not dep["include"]:
        result["include"] = False

    if len(result) == 1:
        return dep["target"]
    return result


class YamlDumper(yaml.SafeDumper):
    """SafeDumper that writes multi-line strings as `|` blocks, so prompts stay readable."""


def represent_str(dumper, text):
    style = "|" if "\n" in text else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", text, style=style)


YamlDumper.add_representer(str, represent_str)


def dump_yaml(config):
    return yaml.dump(config, Dumper=YamlDumper, sort_keys=False, allow_unicode=True, width=1000)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def check_spec(spec):
    """Return a list of problems with the converter's output (empty if it looks fine)."""
    try:
        jsonschema.validate(spec, SCHEMA)
    except jsonschema.ValidationError as e:
        return [f"schema violation: {e.message}"]

    errors = []
    errors += check_paths(spec)
    for target in spec["targets"]:
        errors += check_target(target)
    errors += check_dependencies(spec)
    return errors


def check_paths(spec):
    errors = []
    paths = [t["path"] for t in spec["targets"]]
    final = spec["final_target"]

    duplicates = sorted({p for p in paths if paths.count(p) > 1})
    if duplicates:
        errors.append(f"duplicate target paths: {duplicates}")
    if INPUT_FILE in paths:
        errors.append(f"{INPUT_FILE} is provided by the user and must not be a target")
    if final not in paths:
        errors.append(f"final_target {final!r} is not one of the targets")
    if "$" in final:
        errors.append("final_target must be a concrete path without $VARIABLES")
    return errors


def check_target(target):
    errors = []
    path = target["path"]

    if bool(target["description"]) == bool(target["cmd"]):
        errors.append(f"{path}: exactly one of description/cmd must be set")

    if target["schema"]:
        try:
            json.loads(target["schema"])
        except json.JSONDecodeError as e:
            errors.append(f"{path}: schema is not valid JSON ({e})")

    declared = {v["name"] for v in target["variables"]}
    for name in VAR_REF.findall(path):
        if name not in declared:
            errors.append(f"{path}: path uses ${name} but it is not in variables")

    # escape_description would turn $(...) into literal text, which is never what the model meant.
    if target["description"] and "$(" in target["description"]:
        errors.append(f"{path}: description uses $(...); use variables instead")

    return errors


def check_dependencies(spec):
    """Every dependency must resolve, input.md must be used, and there must be no cycles."""
    errors = []
    paths = [t["path"] for t in spec["targets"]]
    graph = {}  # target path -> paths of the targets it depends on
    uses_input = False

    for target in spec["targets"]:
        graph[target["path"]] = []
        for dep in target["dependencies"]:
            if dep["target"] == INPUT_FILE:
                uses_input = True
                continue
            matches = matching_targets(dep["target"], paths)
            if not matches:
                errors.append(f"{target['path']}: dependency {dep['target']!r} matches no target (and is not {INPUT_FILE})")
            graph[target["path"]] += [m for m in matches if m != target["path"]]

    if not uses_input:
        errors.append(f"no target depends on {INPUT_FILE}, so the user material is never used")

    cycle = find_cycle(graph)
    if cycle:
        errors.append(f"dependency cycle: {' -> '.join(cycle)}")
    return errors


def as_glob(path):
    """sections/$SECTION/about.md -> sections/*/about.md"""
    return VAR_REF.sub("*", path)


def matching_targets(dep, paths):
    """
    Target paths that a dependency refers to.

    A dependency matches a target if it has the same shape (tickets/$ID.md vs tickets/$N.md)
    or if it is one concrete instance of it (tickets/03.md vs tickets/$ID.md).
    """
    return [
        p for p in paths
        if as_glob(p) == as_glob(dep) or fnmatch.fnmatch(dep, as_glob(p))
    ]


def find_cycle(graph):
    """Return one dependency cycle as a list of paths, or None. Plain depth-first search."""
    visiting, done = set(), set()

    def visit(node, chain):
        visiting.add(node)
        for child in graph.get(node, []):
            if child in visiting:
                return chain + [node, child]
            if child not in done:
                cycle = visit(child, chain + [node])
                if cycle:
                    return cycle
        visiting.remove(node)
        done.add(node)
        return None

    for node in graph:
        if node not in done:
            cycle = visit(node, [])
            if cycle:
                return cycle
    return None


def fac_dryrun(yaml_text, final_target):
    """
    Run `fac --dryrun` in a throwaway git repo.

    Returns None if fac isn't installed (check skipped), otherwise a list of errors.
    """
    if shutil.which("fac") is None:
        return None

    with tempfile.TemporaryDirectory() as tmp:
        write_text(Path(tmp) / "fac.yaml", yaml_text)
        write_text(Path(tmp) / INPUT_FILE, "placeholder input\n")
        init_repo(tmp)
        result = subprocess.run(
            ["fac", "--dryrun", final_target],
            cwd=tmp, capture_output=True, text=True, timeout=300,
        )

    if result.returncode != 0:
        output = (result.stdout + result.stderr)[-4000:]  # the tail has the actual error
        return [f"`fac --dryrun {final_target}` failed:\n{output}"]
    return []


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def ask_converter(messages, model):
    """One converter call. Returns (raw_text, spec_or_None, errors, info)."""
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": "fac_workflow", "strict": True, "schema": SCHEMA},
    }
    text, info = chat(messages, model, response_format=response_format)

    try:
        spec = json.loads(text)
    except json.JSONDecodeError as e:
        return text, None, [f"reply is not valid JSON: {e}"], info

    errors = check_spec(spec)
    if errors:
        return text, spec, errors, info

    # Only worth running fac once our own checks pass.
    dryrun_errors = fac_dryrun(dump_yaml(to_fac_config(spec, model)), spec["final_target"])
    info["fac_dryrun"] = "skipped" if dryrun_errors is None else "ran"
    return text, spec, dryrun_errors or [], info


def convert(skill, model=DEFAULT_MODEL, attempts=3):
    """Convert one skill, retrying with error feedback. Returns the converter's JSON spec."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Convert this skill ({skill}) into a fac workflow.\n\n<skill>\n{load_skill(skill)}\n</skill>"},
    ]
    log = {"skill": skill, "model": model, "attempts": []}
    spec, errors = None, []

    for attempt in range(1, attempts + 1):
        text, spec, errors, info = ask_converter(messages, model)
        log["attempts"].append({**info, "errors": errors})

        print(f"[{skill}] attempt {attempt}: {len(errors)} error(s), ${info['cost'] or 0:.4f}, {info['seconds']}s")
        for error in errors:
            print(f"    - {error.splitlines()[0]}")

        if not errors:
            break

        # Show the model its own answer plus the problems, and ask for a fixed version.
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": "The workflow has these problems. Fix all of them and reply with the full corrected JSON:\n- " + "\n- ".join(errors)})

    save_results(skill, model, spec, errors, log)
    if errors:
        raise SystemExit(f"[{skill}] conversion failed after {attempts} attempts; see {RUNS_DIR / skill / 'convert_log.json'}")
    return spec


def save_results(skill, model, spec, errors, log):
    out_dir = RUNS_DIR / skill
    out_dir.mkdir(parents=True, exist_ok=True)

    log["ok"] = not errors
    log["cost"] = sum(a["cost"] or 0 for a in log["attempts"])
    write_text(out_dir / "convert_log.json", json.dumps(log, indent=2))

    if spec is not None:
        write_text(out_dir / "fac.json", json.dumps(spec, indent=2))
    if spec is not None and not errors:
        write_text(out_dir / "fac.yaml", dump_yaml(to_fac_config(spec, model)))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("skills", nargs="*", help=f"skills to convert: {', '.join(list_skills())}")
    parser.add_argument("--all", action="store_true", help="convert every skill")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()

    skills = list_skills() if args.all else args.skills
    if not skills:
        parser.error("give one or more skills, or --all")
    if shutil.which("fac") is None:
        print("warning: `fac` not on PATH; skipping the `fac --dryrun` check", file=sys.stderr)

    for skill in skills:
        convert(skill, args.model, args.attempts)


if __name__ == "__main__":
    main()
