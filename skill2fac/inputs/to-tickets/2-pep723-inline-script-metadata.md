<!-- source: https://github.com/python/peps/blob/main/peps/pep-0723.rst -->

# Task

Below is the Specification section of PEP 723 (inline script metadata). We maintain a Python script runner CLI that does not support it yet. Break the work of supporting this spec (parsing the metadata block, resolving dependencies into an isolated environment, running the script) into implementation tickets.

# Material

Specification
=============

This PEP defines a metadata comment block format loosely inspired [2]_ by
`reStructuredText Directives`__.

__ https://docutils.sourceforge.io/docs/ref/rst/directives.html

Any Python script may have top-level comment blocks that MUST start with the
line ``# /// TYPE`` where ``TYPE`` determines how to process the content. That
is: a single ``#``, followed by a single space, followed by three forward
slashes, followed by a single space, followed by the type of metadata. Block
MUST end with the line ``# ///``. That is: a single ``#``, followed by a single
space, followed by three forward slashes. The ``TYPE`` MUST only consist of
ASCII letters, numbers and hyphens.

Every line between these two lines (``# /// TYPE`` and ``# ///``) MUST be a
comment starting with ``#``. If there are characters after the ``#`` then the
first character MUST be a space. The embedded content is formed by taking away
the first two characters of each line if the second character is a space,
otherwise just the first character (which means the line consists of only a
single ``#``).

Precedence for an ending line ``# ///`` is given when the next line is not
a valid embedded content line as described above. For example, the following
is a single fully valid block:

.. code:: python

    # /// some-toml
    # embedded-csharp = """
    # /// <summary>
    # /// text
    # ///
    # /// </summary>
    # public class MyClass { }
    # """
    # ///

A starting line MUST NOT be placed between another starting line and its ending
line. In such cases tools MAY produce an error. Unclosed blocks MUST be ignored.

When there are multiple comment blocks of the same ``TYPE`` defined, tools MUST
produce an error.

Tools reading embedded metadata MAY respect the standard Python encoding
declaration. If they choose not to do so, they MUST process the file as UTF-8.

This is the canonical regular expression that MAY be used to parse the
metadata:

.. code:: text

    (?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$

In circumstances where there is a discrepancy between the text specification
and the regular expression, the text specification takes precedence.

Tools MUST NOT read from metadata blocks with types that have not been
standardized by this PEP or future ones.

script type
-----------

The first type of metadata block is named ``script`` which contains script
metadata (dependency data and tool configuration).

This document MAY include top-level fields ``dependencies`` and ``requires-python``,
and MAY optionally include a ``[tool]`` table.

The ``[tool]`` table MAY be used by any tool, script runner or otherwise, to configure
behavior. It has the same semantics as the :pep:`tool table <518#tool-table>` in
``pyproject.toml``.

The top-level fields are:

* ``dependencies``: A list of strings that specifies the runtime dependencies
  of the script. Each entry MUST be a valid :pep:`508` dependency.
* ``requires-python``: A string that specifies the Python version(s) with which
  the script is compatible. The value of this field MUST be a valid
  :pep:`version specifier <440#version-specifiers>`.

Script runners MUST error if the specified ``dependencies`` cannot be provided.
Script runners SHOULD error if no version of Python that satisfies the specified
``requires-python`` can be provided.

Example
-------

The following is an example of a script with embedded metadata:

.. code:: python

    # /// script
    # requires-python = ">=3.11"
    # dependencies = [
    #   "requests<3",
    #   "rich",
    # ]
    # ///

    import requests
    from rich.pretty import pprint

    resp = requests.get("https://peps.python.org/api/peps.json")
    data = resp.json()
    pprint([(k, v["title"]) for k, v in data.items()][:10])

Reference Implementation
========================

The following is an example of how to read the metadata on Python 3.11 or
higher.

.. code:: python

   import re
   import tomllib

   REGEX = r'(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$'

   def read(script: str) -> dict | None:
       name = 'script'
       matches = list(
           filter(lambda m: m.group('type') == name, re.finditer(REGEX, script))
       )
       if len(matches) > 1:
           raise ValueError(f'Multiple {name} blocks found')
       elif len(matches) == 1:
           content = ''.join(
               line[2:] if line.startswith('# ') else line[1:]
               for line in matches[0].group('content').splitlines(keepends=True)
           )
           return tomllib.loads(content)
       else:
           return None

Often tools will edit dependencies like package managers or dependency update
automation in CI. The following is a crude example of modifying the content
using the ``tomlkit`` library__.

__ https://tomlkit.readthedocs.io/en/latest/

.. code:: python

   import re

   import tomlkit

   REGEX = r'(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$'

   def add(script: str, dependency: str) -> str:
       match = re.search(REGEX, script)
       content = ''.join(
           line[2:] if line.startswith('# ') else line[1:]
           for line in match.group('content').splitlines(keepends=True)
       )

       config = tomlkit.parse(content)
       config['dependencies'].append(dependency)
       new_content = ''.join(
           f'# {line}' if line.strip() else f'#{line}'
           for line in tomlkit.dumps(config).splitlines(keepends=True)
       )

       start, end = match.span('content')
       return script[:start] + new_content + script[end:]

Note that this example used a library that preserves TOML formatting. This is
not a requirement for editing by any means but rather is a "nice to have"
feature.

The following is an example of how to read a stream of arbitrary metadata
blocks.

.. code:: python

   import re
   from typing import Iterator

   REGEX = r'(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$'

   def stream(script: str) -> Iterator[tuple[str, str]]:
       for match in re.finditer(REGEX, script):
           yield match.group('type'), ''.join(
               line[2:] if line.startswith('# ') else line[1:]
               for line in match.group('content').splitlines(keepends=True)
           )


Backwards Compatibility
=======================

At the time of writing, the ``# /// script`` block comment starter does not
appear in any Python files `on GitHub`__. Therefore, there is little risk of existing
scripts being broken by this PEP.

__ https://github.com/search?q=%22%23+%2F%2F%2F+script%22&type=code


Security Implications
=====================

If a script containing embedded metadata is run using a tool that automatically
installs dependencies, this could cause arbitrary code to be downloaded and
installed in the user's environment.

The risk here is part of the functionality of the tool being used to run the
script, and as such should already be addressed by the tool itself. The only
additional risk introduced by this PEP is if an untrusted script with embedded
metadata is run, when a potentially malicious dependency or transitive
dependency might be installed.

This risk is addressed by the normal good practice of reviewing code
before running it. Additionally, tools may be able to provide
`locking functionality <723-tool-configuration_>`__ to ameliorate this risk.


How to Teach This
=================

To embed metadata in a script, define a comment block that starts with the
line ``# /// script`` and ends with the line ``# ///``. Every line between
those two lines must be a comment and the full content is derived by removing
the first two characters.

.. code:: python

    # /// script
    # dependencies = [
    #   "requests<3",
    #   "rich",
    # ]
    # requires-python = ">=3.11"
    # ///

The allowed fields are described in the following table:

.. list-table::

   * - Field
     - Description
     - Tool behavior

   * - ``dependencies``
     - A list of strings that specifies the runtime dependencies of the script.
       Each entry must be a valid :pep:`508` dependency.
     - Tools will error if the specified dependencies cannot be provided.

   * - ``requires-python``
     - A string that specifies the Python version(s)
       with which the script is compatible.
       The value of this field must be a valid
       :pep:`version specifier <440#version-specifiers>`.
     - Tools might error if no version of Python that satisfies
       the constraint can be executed.

In addition, a ``[tool]`` table is allowed. Details of what is permitted are similar
to what is permitted in ``pyproject.toml``, but precise information must be included
in the documentation of the relevant tool.

It is up to individual tools whether or not their behavior is altered based on
the embedded metadata. For example, every script runner may not be able to
provide an environment for specific Python versions as defined by the
``requires-python`` field.

The :pep:`tool table <518#tool-table>` may be used by any tool, script runner
or otherwise, to configure behavior.
