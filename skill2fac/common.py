"""Shared helpers: paths, skill loading, OpenRouter calls, and git setup."""

import os
import re
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS_DIR = HERE / "skills"
INPUTS_DIR = HERE / "inputs"
RUNS_DIR = HERE / "runs"

DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"
OPENROUTER_URL = "https://openrouter.ai/api/v1"

# The user's material is always given to a fac project under this file name.
INPUT_FILE = "input.md"

# Each vendored file starts with a "<!-- source: <url> -->" line recording where it came from.
SOURCE_COMMENT = re.compile(r"^<!-- source: .*? -->\n", flags=re.M)


def load_dotenv(path=HERE.parent / ".env"):
    """Read KEY=VALUE lines from the repo's .env into os.environ (real env vars win)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_dotenv()


def list_skills():
    """Names of all skills vendored under skills/."""
    return sorted(p.name for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").exists())


def load_skill(name):
    """Return SKILL.md with any references/*.md files appended (source comments removed)."""
    skill_dir = SKILLS_DIR / name
    parts = [read_text(skill_dir / "SKILL.md")]

    for ref in sorted(skill_dir.glob("references/*.md")):
        parts.append(f"# Reference file: references/{ref.name}\n\n{read_text(ref)}")

    text = "\n\n".join(parts)
    return SOURCE_COMMENT.sub("", text).strip() + "\n"


def read_text(path):
    return Path(path).read_text(encoding="utf-8")


def write_text(path, text):
    Path(path).write_text(text, encoding="utf-8")


def chat(messages, model, response_format=None):
    """
    Make one OpenRouter chat completion.

    Returns (reply_text, info), where info has seconds, token counts, and cost in USD.
    """
    from openai import OpenAI  # imported here so the offline tests don't need it

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is not set")
    client = OpenAI(api_key=api_key, base_url=OPENROUTER_URL)

    extra_args = {}
    if response_format is not None:
        extra_args["response_format"] = response_format

    start = time.time()
    result = client.chat.completions.create(
        model=model,
        messages=messages,
        # Same extra_body fac sends to OpenRouter (fac/LLM.py), so both sides are comparable.
        # "usage.include" makes OpenRouter report the real cost of the call.
        extra_body={"provider": {"sort": "latency"}, "usage": {"include": True}},
        **extra_args,
    )

    info = {
        "seconds": round(time.time() - start, 1),
        "prompt_tokens": result.usage.prompt_tokens,
        "completion_tokens": result.usage.completion_tokens,
        "cost": getattr(result.usage, "cost", None),
    }
    return result.choices[0].message.content or "", info


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def init_repo(path):
    """Make `path` a git repo with everything committed. fac refuses to run in a dirty repo."""
    # fac's logger creates .fac.log as soon as fac starts, which would make the repo dirty.
    write_text(Path(path) / ".gitignore", ".fac.log\n")
    git(path, "init", "-q")
    git(path, "config", "user.name", "skill2fac")
    git(path, "config", "user.email", "skill2fac@localhost")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "skill2fac: initial project")
