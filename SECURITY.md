# Security policy

Security fixes target the latest developer preview and the default branch.

Report suspected vulnerabilities privately through
[GitHub private vulnerability reporting](https://github.com/FlightDan/dispatcher-sdk/security/advisories/new).
Include the affected version, reproduction steps, isolation mode, platform and
expected impact. Use synthetic credentials and inputs. The maintainer will
investigate and coordinate disclosure after a fix is available. This preview
has no response-time SLA.

Handlers and scripts run with the worker's OS identity and can access its
resources. Process isolation manages trusted execution. It cannot isolate
hostile code from the host, so run untrusted code under a separate OS identity or
sandbox with appropriate filesystem, network and resource restrictions.

Thread cancellation cannot terminate an external action already in progress.
Effect recovery requires evidence and an isolated or stopped previous worker.
Script output files and SQLite payloads may contain application data. The host
application must manage access controls, quotas and retention.
