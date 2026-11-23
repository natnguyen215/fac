# skill2fac

Converts agent skills (`SKILL.md`) into fac workflows (`fac.yaml`). It then runs both versions on real sample inputs and writes the outputs side by side for manual review.

This directory is standalone. It does not import from `fac/` or `facd/`; it only calls the `fac` CLI.

## How it works

1. **`convert.py`**: makes one structured-output LLM call (system prompt: [converter_prompt.md](converter_prompt.md); schema: [converter_schema.json](converter_schema.json)). The schema walks the model through four stages in order:
   1. classify each skill instruction as operation / constraint / style / approval / control,
   2. plan artifacts,
   3. pick the final target,
   4. write the targets.

   Python then turns `targets[]` into `fac.yaml`. It adds `model:` to every LLM target, marks `input.md` with `in_fac.yaml: false`, and escapes descriptions for fac's bash heredoc templating.

   The result is validated by the JSON schema, graph checks (deps resolve, no cycles, a concrete final target) and `fac --dryrun`. Errors are fed back to the model, up to 3 attempts.
2. **`evaluate.py`**: runs each input in `inputs/<skill>/` two ways:
   - **baseline**: one LLM call, with SKILL.md as the system prompt and the input as the user message;
   - **fac**: a fresh git repo containing `fac.yaml` plus the input saved as `input.md`, built with `fac <final_target>`.

   Both sides use the same model and the same non-interactive ground rules: approvals and questions are dropped, and there are no tools. Writes `runs/<skill>/<input>/compare.md` and `runs/summary.md`.

Skills (vendored under `skills/`, pinned to the commit shown in each file's `<!-- source -->` line): `to-spec`, `to-tickets`, `doc-coauthoring`, `security-threat-model`. The threat-model skill's `references/prompt-template.md` is included because it defines the skill's output format. Inputs are real-world GitHub issues, RFCs, meeting minutes and architecture docs; each has its source at the top.

## Setup

Put `OPENROUTER_API_KEY=...` in the repo's `.env` (gitignored); the scripts read it automatically.

fac needs Linux (bash, jq), so run it in Docker. Build from the repo root:

```bash
docker build -f skill2fac/Dockerfile -t fac-skill2fac .
```

Run any command below inside the container, with the repo mounted:

```bash
docker run --rm -e PYTHONUNBUFFERED=1 -v "C:/Users/natha/fac:/repo" -w /repo/skill2fac fac-skill2fac python3 evaluate.py
```

(Without Docker: any Linux shell with `jq`, then `pip install -e .. -r requirements.txt`.)

## Usage

```bash
python convert.py to-tickets                 # -> runs/to-tickets/fac.yaml (+ fac.json, convert_log.json)
python evaluate.py --input inputs/to-tickets/1-sentry-escalating-issues.md
python evaluate.py --skill to-spec           # all 3 inputs for one skill
python evaluate.py                           # everything; converts any skill not yet converted
python evaluate.py --skill to-spec --reconvert --model deepseek/deepseek-v4.1-flash
```

The default model is `deepseek/deepseek-v4.1-flash` (an OpenRouter id), used for conversion, baseline and fac targets. Override it with `--model`.

`pytest test_convert.py` runs the offline checks (no API calls).
