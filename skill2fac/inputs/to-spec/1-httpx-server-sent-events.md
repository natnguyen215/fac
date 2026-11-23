<!-- source: https://github.com/encode/httpx/issues/1278 -->

# Task

The conversation below is a real GitHub issue discussion about HTTPX (a Python HTTP client library with sync and async APIs). Treat it as the conversation you have already had with the user, and synthesize it into a spec for the feature being discussed.

# Material

## Issue #1278: Server Sent Events

**@lovelydinosaur** (opened 2020-09-10):

It'd be really neat to offer built-in support for server sent events, which are a way for servers to stream events to an HTTP client.

(Similar to WebSockets, but uni-directional)

```python
with httpx.stream("GET", "https://www.example.org/sse") as response:
    for sse in response.iter_sse():
        print(sse.data, sse.event, sse.id, sse.retry)
```

We'd probably also want to include an `sse.json()` helper method.

Useful resources...

* https://www.html5rocks.com/en/tutorials/eventsource/basics/
* https://sysid.github.io/sse/
* https://pgjones.gitlab.io/quart/tutorials/broadcast_tutorial.html

Not sure if this has come up before or not, but it'd be a *really* neat feature for us to offer, for relatively little effort.

---

**@simonw** (2020-10-10):

I really like this. SSE are a under-used feature of the web in my opinion - I could absolutely see myself hooking up a really simple message bus between two machines using SSE served by Starlette and received by HTTPX.

---

**@florimondmanca** (2020-10-10):

FWIW, I had played with SSE myself in Bocadillo at the time, so just linking to the [user docs](https://bocadilloproject.github.io/guide/sse.html#sse-basics) and the [server-side encoding implementation](https://github.com/bocadilloproject/bocadillo/blob/master/bocadillo/sse.py) in case they could be useful here, as some extra reference material.

---

**@havardthom** (2021-04-23):

+1 on this feature. Using FastAPI with sse-starlette + async integration tests with HTTPX testclient. Having a hard time testing my SSE endpoints due to lack of async testclients for SSE

---

**@t94j0** (2021-05-18):

+1 This is the recommended option with FastAPI and sse-starlette. Would be really nice to have this feature

---

**@dusty-phillips** (2021-08-26):

A couple more references:

* https://github.com/aio-libs/aiohttp-sse
* https://github.com/ebraminio/aiosseclient
* https://github.com/sysid/sse-starlette

---

**@harshitsinghai77** (2021-10-09):

Is this issue open? I would like to contribute if this is open. Thanks.

---

**@florimondmanca** (2021-10-10):

@harshitsinghai77 Sure, looks like this is open and contributions and drafts are welcome. :)

---

**@stale[bot]** (2022-02-20):

This issue has been automatically marked as stale because it has not had recent activity. It will be closed if no further activity occurs. Thank you for your contributions.

---

**@lovelydinosaur** (2022-02-21):

Still valid thx, @stale bot.

---

**@stale[bot]** (2022-03-25):

This issue has been automatically marked as stale because it has not had recent activity. It will be closed if no further activity occurs. Thank you for your contributions.

---

**@johtso** (2022-03-25):

Guessing this is still valid..

---

**@lovelydinosaur** (2022-03-25):

We should probably bump up the durations on this stale bot. (Wasn't expecting that it'd repeatedly attempt closes after the first attempt) 😐

---

**@abersheeran** (2022-03-28):

Surprised that this issue has been open for over a year. I just recently added functionality to rpc.py and wrote a code for parsing SSE. If anyone is interested in this, I'll be making a PR to httpx this week.
https://github.com/abersheeran/rpc.py/blob/master/rpcpy/client.py#L211-L243

---

**@lovelydinosaur** (2022-03-29):

Ok. Probably a good plan would be to sketch out the API you'd propose, before submitting a pull request.

---

**@lovelydinosaur** (2022-03-29):

We should also strongly consider if we *really* want to have this as functionality in the core package or not.
Feasible that we should drop this ticket, but allow for a third party implementation.

For example, this'd make for a perfectly reasonable API, without us having to add additional functionality to `httpx` itself...

```python
import httpx
from httpx_sse import iter_sse

with httpx.stream("GET", "https://www.example.org/sse") as response:
    for sse in iter_sse(response):
        print(sse.data, sse.event, sse.id, sse.retry)
```

---

**@florimondmanca** (2022-11-06):

I worked on an `httpx-sse` package that I justed pushed here: https://github.com/florimondmanca/httpx-sse

The API is a bit different from what @tomchristie suggested. This is because the spec requires us to prepare or check some things on the request or the response.

I've thought about making `connect_sse()`/ `aconnect_sse()` handle reconnections, but that would be a lot more work and may not necessarily fit all use cases, as implementation needs may vary. So I've let that to a "how-to" guide in the project README.

```python
import httpx
from httpx_sse import connect_sse

with httpx.Client() as client:
    with connect_sse(client, "http://localhost:8000/sse") as event_source:
        for sse in event_source.iter_sse():
            print(sse.event, sse.data, sse.id, sse.retry)
```

This has not been released to PyPI yet. I'd be happy for folks to try that out first. :-)

Edit: released, https://pypi.org/project/httpx-sse/0.1.0

---

**@MrSalman333** (2023-01-07):

very interested in this
