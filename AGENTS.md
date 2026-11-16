# Project instructions

## Long-running regression tests

- Before starting or waiting for a long-running regression, tell the user the estimated completion time or remaining duration based on available evidence. State when the estimate is uncertain.
- While waiting, check or refresh the test result only when the estimated time arrives; do not repeatedly poll or send unchanged status updates. If it is still running, tell the user the revised estimate based on the available evidence and wait until that time before checking again. An explicit user request to check overrides this schedule.
- Report completion, failure, or another actionable change when it is observed. Do not claim a result or progress solely because the process is still alive.
- Keep the original test scope and timeouts, and preserve the actual output and failure evidence. Do not restart a test merely because an observation timed out.
