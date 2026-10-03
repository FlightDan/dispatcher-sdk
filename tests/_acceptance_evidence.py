"""Retain raw regression evidence locally and in the CI artifact directory."""
import os
from pathlib import Path
import tempfile


def retained_directory(prefix: str) -> Path:
    parent = os.environ.get("SDK_ACCEPTANCE_EVIDENCE_DIR") or None
    if parent:
        Path(parent).mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
