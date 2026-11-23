<!-- source: https://github.com/sharkdp/fd/issues/315 -->

# Task

The conversation below is a real GitHub issue discussion about fd (a Rust command-line alternative to `find`). Treat it as the conversation you have already had with the user, and synthesize it into a spec for the feature being discussed.

# Material

## Issue #315: Finding multiple patterns

**@tjkirch** (opened 2018-07-31):

I'd like to be able to search for multiple patterns, like with grep's -e argument.  It seems (with fd 7.0.0) the only way is to use alternation in the regex pattern, but this can be less clear than multiple arguments, and is harder to build up programmatically.

---

**@sharkdp** (2018-08-03):

Thank you for the feedback!

I certainly see the need for this, but I'm not sure we should introduce a new command-line argument, given that there is a reasonable solution via `fd '(pattern1|pattern2)'`. On the other hand, the analogy to `grep` would be nice. Unfortunately, `-e` is already taken for `--extension`.

Another option to achieve something like this could be the `--path-before-pattern` flag that we were discussing over in #312. This would allow us to use `fd --path-before-pattern . pattern1 pattern2 ...` (possibly with a shortcut for the flag).

---

**@sharkdp** (2018-10-27):

Actually, the `--path-before-pattern` doesn't feel very natural for me. I'd be okay with adding a new `--regexp <PATTERN>` option in analogy to `grep`/`rg`, if someone wants to work on this.

---

**@sharkdp** (2020-04-02):

I'm currently not planning to implement this. Going to close this for now, but happy to reconsider if there is a significant interest in this.

---

**@aschmolck** (2021-02-24):

How about 

```
fd Makefile --or GNuMakefile --or make
```
?

That reads naturally, and it would make it possible to add a git grep or find style boolean query language at some point.

---

**@sharkdp** (2021-03-14):

Let's reopen this for further discussion.

---

**@aschmolck** (2021-03-17):

Here is a concrete example I just did with `find`, I think it would be nice to be able to do the same thing with fd as well:

```
find . -type d -and \( -name node_modules -or -name build \) -exec rm -rf '{}' '+'
```

---

**@sharkdp** (2021-05-16):

I'm definitely against including a full-blown query language with `--and`/`--or`. `fd` was never designed to be this powerful. It's focused on easier use-cases.

Your use-case can be solved by running
```
fd -td '^(node_modules|build)$' -X rm -rf
```
or
```
fd -td node_modules -X rm -rf
fd -td build -X rm -rf
```

Both of which are shorter than the find equivalent (which is not the main issue here though).

---

**@zw963** (2021-07-08):

> I'm definitely against including a full-blown query language with `--and`/`--or`. `fd` was never designed to be this powerful. It's focused on easier use-cases.
> 
> Your use-case can be solved by running
> 
> ```
> fd -td '^(node_modules|build)$' -X rm -rf
> ```
> 
> or
> 
> ```
> fd -td node_modules -X rm -rf
> fd -td build -X rm -rf
> ```
> 
> Both of which are shorter than the find equivalent (which is not the main issue here though).

But, maybe we need a non-regexp OR pattern, following is a example, i guess is not so simple to do with fd.

```
find . \
                -name "* (????-??-??) \[??:??:??\].tar" -o \
                -name "* (????-??-??) \[??:??:??\].bak"
```

Can we support like this:

fd -IH -g '* (????-??-??) \[??:??:??\].tar' -g '* (????-??-??) \[??:??:??\].bak'

---

**@tmccombs** (2021-07-09):

OR is actually pretty easy to do with regexes. 

your example could be done with:

```
fd -IH '.* \(....-..-..\) \[..:..:..\]\.(tar|bak)'
```

AND is more difficult.

---

**@zw963** (2021-07-09):

> OR is actually pretty easy to do with regexes.
> 
> your example could be done with:
> 
> ```
> fd -IH '.* \(....-..-..\) \[..:..:..\]\.(tar|bak)'
> ```
> 
> AND is more difficult.

Yes, i done this like this:

fd -HI '.*\(\d{4}-\d{2}-\d{2}\) \[\d{2}:\d{2}:\d{2}\]\.(tar|bak)'

I think it more obscurely then find or solution anyway.

---

**@minad** (2021-08-07):

@sharkdp I have a use case where it would be very useful if `fd` supported multiple patterns combined with AND. As you write in your https://github.com/sharkdp/fd/issues/315#issuecomment-841869872, you don't want to add a full query language here which is understandable. The combination of multiple regular expressions with OR is no problem. However there is no possibility to search for multiple patterns combined with AND. The reason is also that the Rust regular expression engine does not support lookahead patterns, otherwise one could write `^(?=.*first)(?=.*second)` to search for file names with both first and second in the name. Would you accept a PR which adds support for searching multiple patterns combined with AND?

---

**@sharkdp** (2021-10-08):

To be honest, I haven't really seen a reasonable use case for AND so far. Please let me know if there are any. Not a theoretical use case. A real world, practical use case.

---

**@NightMachinery** (2021-10-08):

[**@sharkdp**](https://github.com/sharkdp) commented on [Oct 9, 2021, 12:36 AM GMT+3:30](https://github.com/sharkdp/fd/issues/315#issuecomment-939115799 "2021-10-08T21:06:29Z - Replied by Github Reply Comments"):
> To be honest, I haven't really seen a reasonable use case for AND so far. Please let me know if there are any. Not a theoretical use case. A real world, practical use case.

Searching for terms where one doesn't know their order. This happens frequently for me; E.g.,`games AND windows`, as I sometimes have `games/Windows`, and sometimes `Windows/games`.

---

**@minad** (2021-10-08):

@sharkdp I have an [Emacs file finder frontend ](https://github.com/minad/consult) which can use find or fd as backend. This frontend supports a matching style we call "orderless" matching, where you enter multiple words/regexps separated by space. Each of the file paths should match all of these regexps. Currently one can achieve this by transforming the regular expressions "word1.*word2|word2.*word1", which obviously does not scale well. Another alternative for AND filtering is to use pipes and run fd first and then grep for the remaining regexps (or instead of grep post-filter in the frontend), but then one loses the performance advantages of fd. The "orderless" style matching is quite popular in Emacs to quickly filter a set of candidates, since as @NightMachinary mentioned, the huge advantage is that the user does not have to know the order of the words/regexps. If this is a reasonable use case depends on your judgement of course. It seems to me that fd aims more at shell users. But I often get the request to support fd in the Emacs frontend by users who prefer fd instead of find for performance reasons.

---

**@sharkdp** (2021-11-14):

Ok, I'm inclined to accept a feature request to support `--and <pattern>`. Before we implement this, we need:

- A short discussion about the command-line option name. What do other tools use?
- A detailed analysis if this could clash with any of the other command-line options or features of `fd`. There are some immediate questions like: what does `fd patternA --and patternB --type f` mean? (we are not going to support the meaning *patternA AND (patternB AND type==file)*).

---

**@zw963** (2021-11-15):

In fact, i thought most of discuss in this thread is about --or, that means, we can search multi-pattern at one command line more easiler.

---

**@sharkdp** (2021-11-15):

Note that there is also #650 and #714. Also, `--or` can usually be worked around easily.

---

**@zw963** (2021-11-15):

I propose we can add --or for now, and let discuss the usage and necessity of --and.

---

**@tmccombs** (2021-11-20):

`--or` isn't really necessary, because you can just use `|` in the pattern to combine multiple patterns. However, there isn't a good way to express `--and` with a single regex. 

To be concrete, a hypothetical `fd foo --or bar` would be equivalent to `fd 'foo|bar'`. Whereas `fd foo --and bar` would need to be converted to something like `fd 'foo.*bar|bar.*foo'` which scales really poorly.

---

**@zw963** (2021-11-20):

> To be concrete, a hypothetical `fd foo --or bar` would be equivalent to `fd 'foo|bar'`

not equivalent.

Because we can use --or with glob-based search

---

**@tavianator** (2021-11-20):

It's equivalent in the sense that every glob can be converted to a regex

---

**@zw963** (2021-11-21):

> It's equivalent in the sense that every glob can be converted to a regex

But in most simple case, glob-based search is more simple than regexp on keystroke

---

**@grothesque** (2021-11-22):

If fd gets both `--or` and `--and` then it should also get `--not` and parens (users would certainly demand it).  We would arrive at something similar to find in terms of complexity.

My understanding is that fd tries to be simpler than find (but at the same time as powerful as feasible).  In that sense, I think it's not too much to ask the advanced user who needs `--or` to simply use regular expressions.

On the other hand, there is really no practical way to work around the lack of `--and`.  Someone who wants to search the file system for three different tags in arbitrary order will have to run fd with a regular expression that combines the six possible permutations in one giant regex.  (I wrote a wrapper script that allows me to run `fd` like this easily and I consider it extremely useful.)

In #889, I suggested that one could deprecate the specification of paths as arguments (as opposed to `--search-path` that I suggest to rename to `--root` and `-r` for brevity).  This would eventually allow to specify multiple search patterns as args. Given that logical OR is already possible within a regex, it would make sense to apply logical AND when multiple patterns are given.

IMHO `fd` would thus gain a much nicer (cleaner and more powerful) UI.

---

**@cheap-glitch** (2022-01-22):

This might be off-topic since it's not strictly about patterns per se, but here's a real-world use case for `--or` that can't be done via a regex:

I have some complex Bash projects with several different types of files (executable scripts, helpers, test modules, etc.) and I want to lint them all at once with `shellcheck`. I can't use plain globs because some files have no extensions and `shellcheck` will error when passed folder names.

This is what I'd like to do:
```
fd -t x --or -e bash --or -e bats -0 | xargs -0 -- shellcheck
```

This can be done with `find`, but without the benefits of automatic VCS exclusions:
```
find \( -type f -and -executable -or -name '*.bash' -or -name '*.bats' \) -print0 | xargs -0 -- shellcheck
```

---

**@sharkdp** (2022-01-22):

> `fd -t x --or -e bash --or -e bats -0 | xargs -0 -- shellcheck`

You can already do this. `-e` already combines in a `or`-sense. In addition, you can use `fd`s `--exec`/`-x` option instead of `xargs`. This will not be just shorter to write, but also faster, because it runs multiple `shellcheck` processes in parallel:
```
fd -tx -ebash -ebats -x shellcheck
```

---

**@cheap-glitch** (2022-01-22):

> You can already do this. -e already combines in a or-sense

Yes, but `-tx` doesn't. To clarify, I want all the files that are executable OR end in `.bash`/`.bats`.

---

**@tmccombs** (2022-01-22):

I think that kind of functionality is out of scope for fd, it would basically involve making an expression language similar to what find has, and make fd significantly more complicated.

---

**@cheap-glitch** (2022-01-22):

> I think that kind of functionality is out of scope for fd, it would basically involve making an expression language similar to what find has, and make fd significantly more complicated.

I totally understand not wanting to add that kind of complexity, but what about a simple global flag? (Sorry if this has already been proposed and rejected somewhere else).

It could be called e.g. `--combine-with` and take 3 possible values:
- `and` to combine all filters with a logical AND
- `or` to combine all filters with OR
- `auto` to use the default "smart" combination logic (so the same as not passing the option at all)

This would probably be easier to implement, and while not as flexible as `find`'s expressions, it would still enable more use cases.

---

**@sharkdp** (2022-01-23):

Thank you for your feedback, but I'm not a fan of the `--combine-with` idea. I'm not sure if that would really allow us to solve a lot of new real world use cases.

What would `fd --combine-with=or -e txt -e md README` do? Would it OR-combine ALL criteria? Including the pattern? So it would search for files with a txt extension, with a md extension OR for files matching README? 

---

Another workaround for the OR use case is to simply use multiple `fd` commands:
```
(fd -t x -0; fd -e bash -e bats -0) | xargs -0 -- shellcheck
```

---

**@097115** (2022-06-02):

@sharkdp,

> Also, --or can usually be worked around easily

Is there any way to search for directories, or files that match specific pattern?

If we search for ALL the files and directories, then, yes, `fd . --type d --type f ~/Documents` can do it. But if we want to get a list of all the directories AND all the `.txt` files, then, as soon as we add `--extension`, like `fd . --type d --type f --extension txt ~/Documents`, fd, as expected, will limit the results to files only. Same happens if we add `--full-path`, like this: `fd --type d --type f --full-path '.*txt$' ~/Documents`.

Of course, combining two different searches into one stream is not a problem. But why spawn two instances? :)

---

**@grothesque** (2022-08-22):

I would like to reinforce the case for an AND operator as opposed to a full implementation of boolean logic (see my [above comment](https://github.com/sharkdp/fd/issues/315#issuecomment-975321964)):

I wrote a script (https://gitlab.kwant-project.org/-/snippets/903, consider it in the public domain) that uses fd as a backend to search for files/directories matching a combination of tags.  The tags of each file/directory are obtained are obtained from the path by treating slashes and dashes as separators.  For example, the file name “pers/2022/bike-repair.org” corresponds to the tags “pers”, “2022”, “bike”, “repair”, as well as “repair.org” (dots are optional tag separators).

Now searching for all events involving my friend “Bob” and the activity “climbing” is as quick as running `ff bob climbing`. (I like to define a short `ff` alias.)  I also have a way to run this directly from within Emacs.

The purpose of this example is not to convince you to organize your home directory in a similar way (although I think that the scheme works very well), but to give one very concrete usage example of fd use where having a way to express an AND relation would be useful.

My script has a `--debug` option that instead of running fd will just print out the command.  As one can imagine, the query length grows exponentially with the number of tags for which to search.  Already with three tags it is getting pretty long (and presumably less efficient):

```
% fdfind-tags --debug a b c
fdfind --full-path --prune --regex '[-/](a)[-/](.*[-/])?(b)[-/](.*[-/])?(c)([-/]|(\.[^/]*)?$)|[-/](a)[-/](.*[-/])?(c)[-/](.*[-/])?(b)([-/]|(\.[^/]*)?$)|[-/](b)[-/](.*[-/])?(a)[-/](.*[-/])?(c)([-/]|(\.[^/]*)?$)|[-/](b)[-/](.*[-/])?(c)[-/](.*[-/])?(a)([-/]|(\.[^/]*)?$)|[-/](c)[-/](.*[-/])?(a)[-/](.*[-/])?(b)([-/]|(\.[^/]*)?$)|[-/](c)[-/](.*[-/])?(b)[-/](.*[-/])?(a)([-/]|(\.[^/]*)?$)'
```

---

**@Uthar** (2022-10-15):

I added multiple pattern finding: https://github.com/Uthar/fd/commit/19c249579cb53736028d2c26839a28e698d462c0

But it's much slower now, 10x. I'm not a Rust expert, maybe someone will help

---

**@QuarticCat** (2022-10-15):

@Uthar I'd like to take a look at the performance problem. How did you benchmark it?

---

**@zw963** (2022-10-15):

> I added multiple pattern finding: [Uthar/fd@19c2495](https://github.com/Uthar/fd/commit/19c249579cb53736028d2c26839a28e698d462c0)
> 
> But it's much slower now, 10x. I'm not a Rust expert, maybe someone will help

Wow, 10x slow, is really not acceptable.

---

**@Uthar** (2022-10-15):

> I'd like to take a look at the performance problem. How did you benchmark it?

Thank you.
I compared these commands:
```
# patched fd
time ./fd --pattern foo .

# upstream fd
time fd foo .
```

---

**@Uthar** (2022-10-15):

> But it's much slower now, 10x. I'm not a Rust expert, maybe someone will help

Ah... I think I was compiling with `cargo build` instead of `cargo build --release`. With release mode the performance is the same as before

I will be using this. But what I did, adding the `--pattern` flag, is too much of a breaking change to make it public.

1. Does anyone want this in upstream?
2. How to add flags similiar to `find -and ... -and .. -and ...`

---

**@tmccombs** (2022-10-16):

Simply timing a single run also isn't very reliable for benchmarking. And if you just run the two commands one after another, the first one you run will probably be significantly slower than the second, because the os will probably cache data from the first run and have it available for the second run. 

https://github.com/sharkdp/fd-benchmarks has some scripts to help benchmark fd with hyperfine.

---

**@sharkdp** (2022-11-21):

closed via #1139
