"""Batteries-included public construction entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .runtime import Handler, InProcessRuntime


class Kernel:
    @classmethod
    def open_sqlite(
        cls,
        path: str | Path,
        handlers: Mapping[Any, Handler],
        **options: Any,
    ) -> InProcessRuntime:
        """Open the complete local stack using only a DB path and handlers."""

        return InProcessRuntime(str(path), handlers, **options)
