<!-- source: this fac repo (commit 2a099e6): AGENTS.md, facd/AGENTS.md, facd/__main__.py, facd/git_routes.py -->

# Task

Threat model the `facd` daemon (repo name: fac, in-scope path: facd/). Intended usage: a developer runs facd locally against a project directory to browse and trigger LLM builds from a web UI. Deployment model, auth expectations and internet exposure are unknown: state assumptions. The repository files below are the only evidence available.

# Material

### `AGENTS.md`

```markdown
# About

fac is a make-like build system for llm based projects.
Targets are defined in a `fac.yaml` file (which acts like the Makefile).
Unlike make, this system also has a daemon facd that runs continuously and exposes a web interface.

```

### `facd/AGENTS.md`

```markdown
# About

This project is a build system for llm based projects.  Targets are defined in a 'fac.yaml' file (which acts like the Makefile). Unlike make, this system has a daemon facd that runs continuously and exposes a web interface.

## Backend structure

The fac folder contains the python library for the build system.

The facd contains a FastAPI webapp that exposes the web interface to fac.

## Frontend structure

All HTML/CSS/Javascript is included in the facd/static folder.
Within this folder are the following subfolders:
- external:
    - contains standard files for external libs
    - the contents of this folder should never be modified by AI agents
- core:
    - tabs.js:
        - defines the main UI interface (2 pane layout, where info is displayed in tabs that can be moved between the panes)
        - does not interact with the backend
    - nodes.js and monitor_files.js:
        - contains code that interacts with the FastAPI backend
        - all of the ui_common files depend on this code
- ui_tabs:
    - contains the main interfaces that the user interacts with
    - each file is in charge of exactly one tab
    - these tabs always use the interface in nodes.js to display files/targets to the user
- ui_common:
    - each of these files modifies some aspect of how a node gets displayed
    - these files only depend on the core/nodes.js interface

## Coding Style

1. Every javascript file must start with a comment that describes what that file does.

1. The style of a tag should never be set directly in HTML/javascript.
    - Instead, you should et the id/class of the tag in HTML/javascript and have a separate CSS file that defines the style for that class.
    - Every file XXX.js should have a corresponding XXX.css that contains these styles.
    - 

```

### `facd/__main__.py`

```python
from contextlib import asynccontextmanager
from importlib.resources import files
from typing import Optional, Set, Any, Literal
import asyncio
import logging
import os
import signal
import sys
import threading
import time

from fac.Fac import Fac, FacSettings
from fac.Logging import logger, with_subtree
import fac.Errors

import git
from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, CliApp, SettingsConfigDict
import hypercorn

from fastapi.responses import FileResponse
from facd import git_routes
from facd import monitor_jobs


################################################################################
# FastAPI setup
################################################################################

@asynccontextmanager
async def lifespan(app: FastAPI):
    if app.args.unsafe_multithread:
        logger.critical('--unsafe_multithread enabled, but build_daemon is not thread safe')
        def run_daemon_in_thread():
            asyncio.run(app.state.build_daemon())
        daemon_task = asyncio.create_task(asyncio.to_thread(run_daemon_in_thread))

    else:
        daemon_task = asyncio.create_task(app.state.build_daemon())

    yield

    # cleanup code here
    logger.warning('FastAPI lifespan ended')
    app.state.path_routes.shutdown()
    await git_routes.shutdown_git_routes()
    await asyncio.sleep(1)

    try:
        daemon_task.cancel()
        await daemon_task

    # When the server shuts down (e.g. by pressing CTRL-C)
    # and the build_daemon is in the middle of a build,
    # these are all common errors that get thrown.
    # The exact error depends on where in the build process shutdown is triggered.
    except (
            asyncio.CancelledError,
            git.exc.GitCommandError,
            fac.Errors.FACError,
            ValueError,
            BrokenPipeError
            ):
        pass

app = FastAPI(title="fac build server", lifespan=lifespan)

# prepare /static mount point
static_path = files("facd") / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")

# prepare templates
templates_path = files("facd") / "static"
templates = Jinja2Templates(directory=str(templates_path))


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/favicon.ico")
async def favicon():
    return FileResponse(static_path / "favicon.ico")


################################################################################
# streaming client logs
################################################################################

# Store connected client queues
log_queues: Set[asyncio.Queue] = set()

class BroadcastHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        for queue in log_queues:
            try:
                queue.put_nowait(msg)
            except asyncio.QueueFull:
                pass

# Attach handler to your build system logger
#logger = logging.getLogger("fac")  # adjust to match your logger name
handler = BroadcastHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(handler)

async def log_generator():
    queue = asyncio.Queue(maxsize=100)
    log_queues.add(queue)
    try:
        yield "data: connected\n\n"
        while True:
            msg = await queue.get()
            yield f"data: {msg}\n\n"
    finally:
        log_queues.discard(queue)

@app.get("/logs_stream")
async def stream_logs():
    return StreamingResponse(
        log_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

@app.get('/list_targets', response_model=dict[str, Any])
async def list_targets():
    '''
    Returns a dictionary of targets defined in the 'fac.yaml' file.
    The keys are targets and values are config information describing how to build the targets.

    ---

    A target is a string that may contain shell-like variables
    that describes a formula for generating paths.

    For example:

    1. The target "example.json" contains no variables and will always resolve to path "example.json".

    2. The target "chapters/$CHAPTER/outline.json" with CHAPTER=['0001', '0002', '0003']
        will resolve to the three paths:
        - 'chapters/0001/outline.json'
        - 'chapters/0002/outline.json'
        - 'chapters/0003/outline.json'

    The web API exposes methods for working with targets and their corresponding paths,
    but does not expose an interface for working with the variables.
    The variable definitions are exposed in the config values returned by this endpoint for debug purposes,
    but they are processed internally by the webserver and shouldn't be used in the web app.
    Any web applications must be built to handle arbitrary paths existing for each target.
    '''
    return app.state.targets_dict


class AddTargetRequest(BaseModel):
    target: str
    required_for: Optional[Any] = None
    include_prompt: Optional[str] = None
    include_old: bool = False
    include_paths: Optional[Any] = None
    tasks: Set[str] = {'build'}


@app.post('/add_target')
async def add_target_endpoint(request: AddTargetRequest):
    '''
    Registers a target with the build system.

    Arguments:
    - target (str): the target to be built; all variables must be specified; supports globstar (**)-style pattern matching
    - include_prompt (str): allows specifying additional build instructions for the target
    - include_old (bool): should the old file be included if rebuilding?
    - tasks [str]:
        - "build": (default) build the file only if needed
        - "overwrite": always build the file, overwriting existing contents
        - "dryrun": register the file with the build system, but do not build
    '''
    app.state.add_target(
        target=request.target,
        required_for=request.required_for,
        include_prompt=request.include_prompt,
        include_old=request.include_old,
        include_paths=request.include_paths,
        tasks=request.tasks,
    )
    return {"status": "success"}

################################################################################
# run the server
################################################################################

class FacdSettings(FacSettings):
    '''Settings for the facd daemon, including server and build options.'''
    model_config = SettingsConfigDict(
        cli_parse_args=True,
        cli_prog_name='facd',
        cli_implicit_flags=True,
        env_prefix='FAC_',
    )
    server: Literal['hypercorn', 'uvicorn'] = 'hypercorn'
    unsafe_multithread: bool = False
    dryrun_target: str = '**'

def main():
    settings = FacdSettings()

    app.args = settings
    logger.setLevel(settings.loglevel)

    # register state routes
    try:
        state = Fac(settings)
        app.state = state
    except fac.Errors.FACError:
        return 1

    # perform a dryrun to register files with facd
    state.add_target(settings.dryrun_target, tasks=set())

    # register routes
    app.include_router(state.router)
    app.include_router(state.path_routes.router)
    app.include_router(git_routes.router)
    monitor_jobs.set_build_state(state)
    app.include_router(monitor_jobs.router)

    # start the web server
    if settings.server == 'hypercorn':
        from hypercorn.asyncio import serve
        from hypercorn.config import Config
        config = Config()
        # NOTE:
        # There was a bad bug when using IPv4 that caused connections to localhost
        # to sometimes break in very heisenbugish ways.  Binding to IPv6 seems to
        # solve this problem.
        config.bind = ['[::]:8080']
        config.graceful_timeout = 2.0

        async def _run():
            shutdown_event = asyncio.Event()
            loop = asyncio.get_running_loop()

            def _handle_signal():
                logger.error('Force exiting...')
                shutdown_event.set()
                os._exit(1)

            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, _handle_signal)
            await serve(app, config, shutdown_trigger=shutdown_event.wait)

        asyncio.run(_run())

    elif settings.server == 'uvicorn':
        import uvicorn
        uvicorn.run(
                app,
                host='::',
                port=8080,
                timeout_graceful_shutdown=5,
                log_level='warning',
                )

if __name__ == '__main__':
    main()

```

### `facd/git_routes.py`

```python
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import subprocess
import json
import os
from watchfiles import awatch, Change

router = APIRouter()

# Track subscribers for git events
_git_subscribers: set = set()
_watch_task = None
_stop_event = None
_shutdown = False


class CheckoutRequest(BaseModel):
    ref: str


def _get_stop_event():
    global _stop_event
    if _stop_event is None:
        _stop_event = asyncio.Event()
    return _stop_event


def _get_diff_stats(commit_hash: str) -> list[dict]:
    """
    Get diff stats for a commit compared to its parent.
    
    Returns a list of dicts, each containing:
      - path: file path
      - additions: number of lines added
      - deletions: number of lines removed
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--numstat", f"{commit_hash}^", commit_hash],
            capture_output=True,
            text=True,
            check=True
        )
        
        stats = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split('\t')
                if len(parts) == 3:
                    additions, deletions, path = parts
                    # Handle binary files (shown as '-')
                    stats.append({
                        "path": path,
                        "additions": int(additions) if additions != '-' else 0,
                        "deletions": int(deletions) if deletions != '-' else 0
                    })
        return stats
    except subprocess.CalledProcessError:
        # This can fail for root commits or other edge cases
        return []


def _get_git_log(limit: int = 100) -> list[dict]:
    """
    Get git log as a list of commit dicts, including all commits from all refs and reflog.
    
    Each dict contains:
      - hash: short commit hash
      - full_hash: full commit hash
      - message: full commit message
      - author: author name
      - date: ISO format date
      - parents: list of parent full hashes
      - branches: list of branch names pointing to this commit
      - tags: list of tag names pointing to this commit
      - is_head: whether HEAD points to this commit
      - diff_stats: list of file change stats (path, additions, deletions)
    """
    try:
        # Get all commits from --all --reflog to include orphaned commits
        result = subprocess.run(
            [
                "git", "log",
                "--all", "--reflog",
                "--format=%h%x00%H%x00%an%x00%aI%x00%P%x00%B%x00%x01"
            ],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Get branch info: which branches point to which commits
        branch_result = subprocess.run(
            ["git", "branch", "-a", "--format=%(objectname:short) %(refname:short)"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Get tag info
        tag_result = subprocess.run(
            ["git", "tag", "--format=%(objectname:short) %(refname:short)"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Get current HEAD
        head_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        head_hash = head_result.stdout.strip()
        
        # Build branch map: hash -> list of branch names
        branch_map: dict[str, list[str]] = {}
        for line in branch_result.stdout.strip().split('\n'):
            if line:
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    commit_hash, branch_name = parts
                    if commit_hash not in branch_map:
                        branch_map[commit_hash] = []
                    branch_map[commit_hash].append(branch_name)
        
        # Build tag map: hash -> list of tag names
        tag_map: dict[str, list[str]] = {}
        for line in tag_result.stdout.strip().split('\n'):
            if line:
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    commit_hash, tag_name = parts
                    if commit_hash not in tag_map:
                        tag_map[commit_hash] = []
                    tag_map[commit_hash].append(tag_name)
        
        # Parse commits, deduplicating by full_hash
        commits = []
        seen_hashes = set()
        raw_commits = result.stdout.split('\x01')
        
        for raw_commit in raw_commits:
            raw_commit = raw_commit.strip()
            if not raw_commit:
                continue
            
            parts = raw_commit.split('\x00')
            if len(parts) >= 6:
                short_hash = parts[0]
                full_hash = parts[1]
                author = parts[2]
                date = parts[3]
                parents_str = parts[4]
                message = parts[5].strip()
                
                # Skip duplicates
                if full_hash in seen_hashes:
                    continue
                seen_hashes.add(full_hash)
                
                parents = parents_str.split() if parents_str else []
                
                commits.append({
                    "hash": short_hash,
                    "full_hash": full_hash,
                    "message": message,
                    "author": author,
                    "date": date,
                    "parents": parents,
                    "branches": branch_map.get(short_hash, []),
                    "tags": tag_map.get(short_hash, []),
                    "is_head": short_hash == head_hash,
                    "diff_stats": _get_diff_stats(full_hash)
                })
        
        return commits
        
    except subprocess.CalledProcessError:
        return []


async def _broadcast_git_state():
    """Send current git state to all subscribers."""
    commits = _get_git_log()
    data = json.dumps(commits)
    
    dead_subscribers = set()
    for queue in _git_subscribers:
        try:
            await queue.put(data)
        except Exception:
            dead_subscribers.add(queue)
    
    _git_subscribers.difference_update(dead_subscribers)


def _no_filter(change: Change, path: str) -> bool:
    """Accept all file changes, including .git directory."""
    return True


async def _watch_git_directory():
    """
    Watch the .git directory for changes and notify subscribers.
    
    When changes are detected, sends the full commit list to all subscribers.
    """
    global _shutdown

    git_dir = ".git"
    if not os.path.exists(git_dir):
        return
    
    stop_event = _get_stop_event()

    try:
        async for changes in awatch(git_dir, stop_event=stop_event, watch_filter=_no_filter):
            if _shutdown:
                break
            await _broadcast_git_state()
    except Exception:
        pass


def _ensure_watch_task():
    """Ensure the git directory watch task is running."""
    global _watch_task
    if _watch_task is None or _watch_task.done():
        _watch_task = asyncio.create_task(_watch_git_directory())


async def _git_event_generator(request: Request):
    """Generate SSE events for git changes."""
    queue: asyncio.Queue = asyncio.Queue()
    _git_subscribers.add(queue)
    _ensure_watch_task()
    
    try:
        # Send initial state
        commits = _get_git_log()
        yield f"data: {json.dumps(commits)}\n\n"
        
        while True:
            if await request.is_disconnected():
                break
            
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {data}\n\n"
            except asyncio.TimeoutError:
                # Send keepalive
                yield ": keepalive\n\n"
    finally:
        _git_subscribers.discard(queue)


@router.get("/git_events")
async def git_events(request: Request):
    """
    SSE endpoint for git repository changes.
    
    Sends a JSON array of commit objects whenever the repository changes.
    Includes all commits reachable from any branch, tag, or reflog entry,
    suitable for rendering: git log --oneline --graph --all --decorate --reflog
    
    Each commit object contains:
      - hash: short commit hash
      - full_hash: full commit hash  
      - message: full commit message
      - author: author name
      - date: ISO format date
      - parents: list of parent full hashes
      - branches: list of branch names pointing to this commit
      - tags: list of tag names pointing to this commit
      - is_head: whether HEAD points to this commit
      - diff_stats: list of file change stats, each containing:
          - path: file path
          - additions: number of lines added
          - deletions: number of lines removed
    """
    return StreamingResponse(
        _git_event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/git_checkout")
async def git_checkout(request: CheckoutRequest):
    """
    Checkout a specified commit hash, branch, or tag.
    
    Args:
        ref: The commit hash, branch name, or tag name to checkout
        
    Returns:
        JSON object with:
          - success: boolean indicating if checkout succeeded
          - message: success or error message
    """
    try:
        result = subprocess.run(
            ["git", "checkout", request.ref],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Broadcast the new git state to all subscribers
        await _broadcast_git_state()
        
        return {
            "success": True,
            "message": f"Successfully checked out '{request.ref}'"
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "message": e.stderr.strip() or f"Failed to checkout '{request.ref}'"
        }


@router.on_event("shutdown")
async def shutdown_git_routes():
    """Clean up on shutdown."""
    global _shutdown, _watch_task
    _shutdown = True
    stop_event = _get_stop_event()
    stop_event.set()
    if _watch_task:
        _watch_task.cancel()
        try:
            await _watch_task
        except asyncio.CancelledError:
            pass

```
