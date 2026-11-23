<!-- source: https://github.com/junegunn/fzf/issues/3372 -->

# Task

Document type: feature proposal. Audience: the fzf maintainer and plugin authors. Desired impact: the maintainer can decide whether to accept a headless mode, with use cases, a proposed interface, and open questions laid out. No template. The context dump is the GitHub discussion below.

# Material

## Issue #3372: Feature request: headless mode

**@tw4452852** (opened 2023-07-17):

<!-- ISSUES NOT FOLLOWING THIS TEMPLATE WILL BE CLOSED AND DELETED -->

<!-- Check all that apply [x] -->

- [x] I have read through the manual page (`man fzf`)
- [x] I have the latest version of fzf
- [x] I have searched through the existing issues

It would be nice to have a headless mode when writting some scripts for `fzf`. 
Right now, we already setup a http server to accept actions, I think the only missing part is
getting result list through `GET`.

The scenario in which I find this use case is that, I usually launch `fzf` from other programs,
and usually I don't want to run it interactively. I think if headless mode is enabled, we could
launch it with `fzf --listen > /dev/null` and all the interactions are done through HTTP request/response.
What do you think about this?

---

**@junegunn** (2023-08-03):

I'm not sure about this. Are you trying to build your own UI for fzf?

---

**@tw4452852** (2023-08-03):

Yes

---

**@nkh** (2023-08-24):

@junegunn I'll second this request. I use fzf, in multiple places,  in my file manager, in the main view I let fzf take over but it's sub optimal because the previews are much better in the file manager and I can't  have all the previews in fzf (some are graphical, other open extra programs in a different terminal).

Not sure about he web interface, maybe a simple protocol where one sends commands on std, in a format different from files, and read results on stdout, this would make it simple to run fzf in the background, results can be read in chunks, IE if 35 000 files match fzf writes nothing to stdout, only when the main program requests a chunk of file are they output.

---

**@tw4452852** (2023-08-24):

Another use case will be launching `fzf` remotely, this is extremely useful when working remotely.

---

**@junegunn** (2023-09-03):

0f50dc848e58b47408713c2c31f2be73287c030a is what I can offer at the moment. Since I don't have a solid use case myself, I don't know if the suggested JSON schema is sufficient. Please give it a try and let me know what you think.

---

**@nkh** (2023-09-03):

@junegunn if I understand the patch right, this only returns a status but there no way yet to change the query or get a subset of the results.

without wanting to complicate it at this stage, I wonder how the the user will be emulated:
- send specific commands, providing some REST API
- send keyboard keys, IE: emulating user input

In any case I'll pull this and test it, I'm curious about what the contents of 'Matches' is (hopping it's not the strings yet), and will be happy to test this as much as you need.

I'll also start integrating this in my application so I can give "real" usage feedback.

---

**@junegunn** (2023-09-03):

> @junegunn if I understand the patch right, this only returns a status but there no way yet to change the query or get a subset of the results.

You've never used `--listen` before? You can invoke any action that can be specified in `--bind`. e.g. `curl localhost:6266 -d 'change-query:foo'`

---

**@nkh** (2023-09-03):

No, I discovered it in your answer in this issue.

I notice that matches is limited to 100 matches. I understand that a a limit had to be set.

If possible I would like to see the possibility to:
- set the number of matches to be returned, best would be with start index and end index
     - with the possibility to give 0 for both
- same thing for selection

the match entries consist of:
- text
- index

what is the index supposed to be used for?.

---

**@junegunn** (2023-09-07):

I'll probably decide to add `limit` and `offset` parameters, which should be familiar to anyone with SQL experience.

> what is the index supposed to be used for?

It's the value of `{n}`. See #1482 for the motivation behind it.

---

**@nkh** (2023-12-20):

@junegunn I finally integrated fzf directly in my file manger; thank you for the help.

I notice that there's a slight delay before one can get data from fzf, around 1/10 of second. 

![screenshot_2023-12-20_19-12-29](https://github.com/junegunn/fzf/assets/45409/c64d8353-28f3-4143-9956-318069a12eea)

---

**@donvince** (2024-01-22):

I think the `--filter` parameter gives a suitable headless experience

---

**@metametapod** (2024-02-20):

`fzf --filter` currently errors out when no TTY is set, e.g.:

```sh
$ fzf --filter= </dev/null
$ echo $status
1
```

This is the case for example when invoking from AppleScript or JXA.

To workaround, you can use:
```sh
$ unbuffer -p fzf --filter=
```

See https://stackoverflow.com/a/32981392

---

**@junegunn** (2024-02-20):

> fzf --filter currently errors out when no TTY is set, e.g.:

Exit status 1 means "no match". 

https://github.com/junegunn/fzf/blob/ca747a2b5465961b23aa09606412877dd482a874/man/man1/fzf.1#L875-L882

You're feeding /dev/null, so there can't be any match.

---

**@metametapod** (2024-02-20):

The workaround allows `</dev/null` without the error:

```sh
$ unbuffer -p fzf --filter= </dev/null
$ echo $status
0
```

Example broken AppleScript:

```sh
osascript -e 'do shell script "fzf --filter="'
```

Fixed by:

```sh
osascript -e 'do shell script "unbuffer -p fzf --filter="'
```

---

**@JimmyZJX** (2025-05-18):

Firstly thank @junegunn for implementing the GET API!

To follow up on this thread, I recently worked on integrating fzf into my VSCode extension (https://github.com/JimmyZJX/leaderkey).

What I want is a **true headless mode** where fzf does not render anything and **does not require tty**, while serving the query and sort logic in the existing HTTP server.

Most of my experimental code works reasonably good after spending >8 hours figuring out how to create a fake tty for Linux/Windows around fzf. In the end, it's still not perfect
- on Windows, a terminal is poped up in the background
- on Linux/MacOS, it requires the "script" executable

I wonder how much effort is there and how likely the community will support a flag like `--headless` that disables all the rendering? If maintainers are happy to accept it, I can also try my best to learn the codebase and make a PR.

---

**@JimmyZJX** (2025-06-30):

I tried to use the `script` executable to provide a fake tty, but the behavior is not reliable and sometimes weird.

I basically called this
```
script --quiet --return --command "fzf --listen $PORT" /dev/null
```
and interact with it via HTTP. It works fine. (Obviously you need to test without a pty, otherwise fzf would just behave correctly)

However, adding an environment variable `FZF_DEFAULT_COMMAND="fd --type f"` causes fzf to stuck in a weird state, where I always get nothing when polling for results (`GET /`), like this
```
{"reading":false,"progress":100,"query":" ab","position":0,"sort":true,"totalCount":0,"matchCount":0,"current":null,"matches":[],"selected":[]}
```

I've run into similiar states when pty is not set up properly. But in this case, even wrapping with `script` does not work.

Wish you have some insights 🙏 @junegunn 

I also spent a while coming up with a reproduction. I cannot find good ways to explain what happened.

```py
import subprocess
import time

FZF_PROG =  "fzf"
SCRIPT_PROG = "/usr/bin/script"

fzf_args = [FZF_PROG, "--listen",  "10010"]

script_args = [SCRIPT_PROG,
            "--quiet",
            "--return",
            "--command",
            " ".join(fzf_args),
            "/dev/null"]

proc = subprocess.Popen(script_args,
            # behavior is different with or without the following line
            env={"FZF_DEFAULT_COMMAND": "fd --type f"},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

time.sleep(1)

# or curl/wget instead
import requests
print(requests.get("http://localhost:10010").text)
```

The behavior is different with or without the environment variable for me. Without the env var, I see reasonable results. With it, I got empty results, like the JSON above.

---

**@JimmyZJX** (2025-07-01):

Ok... after digging into the issue I realize that the shell option fzf gets by default becomes `sh` somehow, which result in a silent error message:
```
exec: "sh": executable file not found in $PATH
```

By adding the flag
```
--with-shell '/bin/bash -c'
```
fixes the issue

I found the issue in `reader.go`. See screenshot

![Image](https://github.com/user-attachments/assets/b5c80d91-dcab-49be-ae40-2af1b9600d60)

---

**@junegunn** (2025-07-02):

> fzf gets by default becomes `sh` somehow

https://github.com/junegunn/fzf/blob/ba035f2a7649ab2c66ae320ef9a6e11e64813f9b/src/util/util_unix.go#L21-L32

1. If `--with-shell` is given, fzf uses it
1. then fzf tries to use `$SHELL`
1. if the variable is empty, it chooses `sh`

So in your environment, `$SHELL` is not defined, and `sh` is not in `$PATH`?

---

**@JimmyZJX** (2025-07-02):

I just realized that I've been quite dumb. I spawned processes without inheriting any environment variable, which caused these logic to fail and resulted in `sh` with no `$PATH` set. My bad!

On the `fzf` side I'd expect to see error messages somewhere but I also understand it might be hard to fit into the existing fancy UI.

---

**@iolpltuisciaoln** (2026-01-23):

Hello all, want to give my voice for headless mode as i'm struggle to build advanced ripgrep utility.
The idea is while headless fzf can accumulate and filter results from (e.g.) fdfind, another headless fzf could do a ripgrep over results and the third one with TUI can switch/display results/ between them (something like an example from `fzf/ADVANCED.md`).

---

**@miaLDN** (2026-08-07):

> 1. If `--with-shell` is given, fzf uses it
> 2. then fzf tries to use `$SHELL`
> 3. if the variable is empty, it chooses `sh`
> 
> So in your environment, `$SHELL` is not defined, and `sh` is not in `$PATH`?

### ENV SHELL

```bash
 $ declare -p SHELL
declare -x SHELL="BASH"
``` 
### fzf preview fails

```txt
exec: "BASH": executable file not found in $PATH
 ``` 

### fzf version

```bash
$ fzf --version
0.74.0 (6765f464)
  ```
