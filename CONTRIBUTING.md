# Contributing

Report reproducible bugs and propose API changes through
[GitHub Issues](https://github.com/FlightDan/dispatcher-sdk/issues).
Include the SDK version, operating system, Python version, isolation mode and a
small example. Use synthetic inputs and leave out credentials, private payloads
and logs.
Discuss changes to persistence or recovery guarantees before implementing them.

## Local development

Create and activate a Python 3.10+ virtual environment, then run:

```sh
python -m pip install -e . build wheel "setuptools>=68"
python -m unittest discover -s tests -v
python scripts/check_docs.py
python examples/kernel_task.py
python examples/dependent_tasks.py
python examples/effect_recovery.py
```

On POSIX hosts with fork support or native Windows, also run:

```sh
python examples/sdk_script_wakeup.py
```

The tests rebuild the source archive and run the runtime tests against an
installed wheel in a fresh environment outside the checkout. Process tests skip
hosts that lack the required platform capability; thread-mode and persistence
tests still run there.

## Documentation

Keep detailed API contracts in `docs/`, bilingual user guides in `wiki/`, and
English Agent integration guidance in `DocsforAgents/`. See
[Wiki maintenance and publication](docs/WIKI_MAINTENANCE.md) for link checks,
export and publication steps.

## Building a candidate

```sh
python -m build
python -m pip install --force-reinstall --no-deps dist/dispatcher_sdk-0.6.0-py3-none-any.whl
```

The version shown matches this checkout. For a later release, use that release's
wheel filename. Verify both the wheel and the source archive, run tests and
examples against the installed candidate, and attach SHA-256 checksums to the
GitHub prerelease. `RELEASING.md` describes the release workflow.

Keep changes focused. In the pull request, describe the behavior, tests,
platform limits and compatibility impact. Add regression coverage for changes
to lease/fence handling, concurrency, persistence, replay and external effects.
Keep business routing outside the Kernel. Import through `dispatcher_sdk`;
the `agent_dispatcher` application is not part of this repository.

Contributions use the project's Apache-2.0 license. Preserve source attribution
when adding third-party material. Report security problems using
[SECURITY.md](SECURITY.md), not public issues.
