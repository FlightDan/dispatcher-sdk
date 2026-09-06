# Contributing

Report reproducible bugs and propose API changes through
[GitHub Issues](https://github.com/FlightDan/dispatcher-sdk/issues).
Include the SDK version, operating system, Python version, isolation mode and a
small example. Use synthetic inputs; omit credentials, private payloads and logs.
Discuss changes to persistence or recovery guarantees before implementing them.

## Local development

Create and activate a Python 3.10+ virtual environment, then run:

```sh
python -m pip install -e . build wheel
python -m unittest discover -s tests -v
python scripts/check_docs.py
python examples/kernel_task.py
python examples/dependent_tasks.py
python examples/effect_recovery.py
```

On POSIX hosts with fork support, also run:

```sh
python examples/sdk_script_wakeup.py
```

Tests include a source archive rebuild and a separate installed-wheel consumer.
That consumer runs the runtime tests in a fresh environment outside the checkout.
Platform-specific process tests are skipped on hosts without the required
capability; thread-mode and persistence tests still run there.

## Building a candidate

```sh
python -m build
python -m pip install --force-reinstall --no-deps dist/dispatcher_sdk-0.5.1-py3-none-any.whl
```

The version shown matches this checkout. For a later release, use that release's
wheel filename. Verify both the wheel and the source archive, run tests and
examples against the installed candidate, and attach SHA-256 checksums to the
GitHub prerelease. `RELEASING.md` describes the release workflow.

Keep changes focused. Describe observable behavior, tests, platform limits and
any compatibility impact in a pull request. Add regression coverage for changes
to lease/fence handling, concurrency, persistence, replay and external effects.
Keep business routing outside the Kernel. Import through `dispatcher_sdk`;
the `agent_dispatcher` application is not part of this repository.

Contributions use the project's Apache-2.0 license. Preserve source attribution
when adding third-party material. Report security problems using
[SECURITY.md](SECURITY.md), not public issues.
