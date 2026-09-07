# Source provenance

Dispatcher SDK was extracted on 2026-09-07 from the Kernel and generic SDK in
[FlightDan/agent_dispatcher](https://github.com/FlightDan/agent_dispatcher).
The source checkout's HEAD was `9cea4802dc70e01837704f1126a085e115b65499`.
The extracted working tree also included uncommitted SDK host, script and
notification changes, so that commit alone does not reproduce the extracted
files. `SOURCE_MANIFEST.json` records each copied runtime Python file's source
and standalone SHA-256 hashes at extraction time.

The extraction renames the distribution to `dispatcher-sdk` and the import
namespace to `dispatcher_sdk`. It uses a self-contained `src` layout, adapts SDK
unit tests, filters documentation for SDK consumers, and adds standalone examples
and release tooling. The original application's workflows, CLI, WebUI, run
artifacts and Git history are not included.

The core runtime uses the Python standard library. Build tools and CI actions
are development dependencies and are not bundled in the wheel. `LICENSE` and
`NOTICE` retain the Apache-2.0 license and original SDK copyright attribution.
The manifest records source-file provenance even for files without a separate
copyright header.
