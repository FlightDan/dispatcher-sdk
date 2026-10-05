"""Recover physical script-output facts after confirmed native containment.

This owner neither runs scripts nor resolves their effects. Its single retained
worker may outlive a caller blocked in filesystem I/O; storage stays owned until
the original fact has been published. A failed publication never resamples files.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sqlite3
import stat
import threading
import time
from typing import Any

from .._sqlite_errors import is_sqlite_contention


class _ReadDeadline(TimeoutError):
    pass


def _text(value: object, limit: int = 256) -> str:
    try:
        rendered = str(value)[:limit]
        return rendered.encode("utf-8", "replace")[:limit].decode("utf-8", "ignore")
    except BaseException:
        return "error rendering unavailable"


class ScriptOutputRecovery:
    def __init__(self, kernel_path: str | Path, settlement_journal: Any):
        self._uri = Path(kernel_path).absolute().as_uri() + "?mode=ro"
        self._journal = settlement_journal
        self._condition = threading.Condition(threading.RLock())
        self._operation = threading.Lock()
        self._record: dict[str, Any] | None = None
        self._fact: dict[str, Any] | None = None
        self._worker: threading.Thread | None = None
        self._request: float | None = None
        self._sequence = 0
        self._completed = 0
        self._published = False
        self._error: str | None = None

    def pending(self, execution_id: str | None = None, attempt: int | None = None,
                fence: int | None = None) -> bool:
        """Report actual local ownership, including a blocked worker."""
        with self._condition:
            if self._record is None:
                return False
            identity = self._record["identity"]
            return all(value is None or identity[name] == value for name, value in
                       (("execution_id", execution_id), ("attempt", attempt), ("fence", fence)))

    def recover(self, deadline: float) -> dict[str, Any]:
        """Discover at most one durable obligation and service its original key."""
        return self._service(deadline, discover=True)

    def drain(self, deadline: float) -> bool:
        """Retry/join the retained owner; return True while cleanup is pending."""
        return self._service(deadline, discover=False)["pending"]

    def _service(self, deadline: float, *, discover: bool) -> dict[str, Any]:
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ValueError("deadline must be a finite absolute monotonic time")
        if not self._operation.acquire(timeout=max(0., deadline - time.monotonic())):
            return {"pending": self.pending(), "error": "recovery admission deadline elapsed"}
        try:
            # A published thread must actually exit before its owner is released
            # or any new worker can be started.
            with self._condition:
                old = self._worker if self._published else None
            if old is not None:
                old.join(max(0., deadline - time.monotonic()))
                with self._condition:
                    if not old.is_alive():
                        self._record = self._fact = self._worker = None
                        self._published = False
            with self._condition:
                empty = self._record is None
            if empty and discover and deadline > time.monotonic():
                try:
                    records = self._journal.pending_script_output(
                        timeout_seconds=min(.1, deadline - time.monotonic()))
                except Exception as error:
                    return {"pending": False, "discovery_pending": True,
                            "error": _text(error)}
                if records:
                    with self._condition:
                        self._record = records[0]
                        self._error = None
            with self._condition:
                if self._record is None:
                    return {"pending": False}
                if not self._published and deadline > time.monotonic():
                    self._sequence += 1
                    sequence = self._sequence
                    self._request = deadline
                    if self._worker is None:
                        worker = threading.Thread(target=self._work,
                            name="dispatcher-script-output-recovery", daemon=True)
                        self._worker = worker
                        try:
                            worker.start()
                        except BaseException:
                            self._worker = None
                            self._request = None
                            raise
                    self._condition.notify_all()
                    while self._completed < sequence and deadline > time.monotonic():
                        self._condition.wait(deadline - time.monotonic())
                published = self._published
                worker = self._worker
            if published and worker is not None:
                worker.join(max(0., deadline - time.monotonic()))
                with self._condition:
                    if not worker.is_alive():
                        self._record = self._fact = self._worker = None
                        self._published = False
            with self._condition:
                return {"pending": self._record is not None, "error": self._error}
        finally:
            self._operation.release()

    def _work(self) -> None:
        while True:
            with self._condition:
                while self._request is None:
                    self._condition.wait()
                deadline, sequence = self._request, self._sequence
                self._request = None
                record, fact = self._record, self._fact
            try:
                if fact is None:
                    fact = self._capture(record, deadline)
                    with self._condition:
                        self._fact = fact
                if time.monotonic() >= deadline:
                    raise _ReadDeadline("script output publication deadline elapsed")
                self._journal.record_script_output(record["identity"], fact,
                    timeout_seconds=deadline - time.monotonic())
            except Exception as error:
                with self._condition:
                    self._error = _text(error)
                    self._completed = sequence
                    self._condition.notify_all()
                # Keep the very same worker and fact, awaiting an explicit
                # maintenance call. No autonomous polling or renewed budget.
                continue
            with self._condition:
                self._published = True
                self._error = None
                self._completed = sequence
                self._condition.notify_all()
            return

    def _capture(self, record: dict[str, Any], deadline: float) -> dict[str, Any]:
        key = record["identity"]
        marker = record["evidence"]["script_output_recovery"]
        identity = marker.get("identity")
        fact: dict[str, Any] = {"identity": identity, "cleanup_confirmed": True,
            "source": "script_artifact_after_native_cleanup", "sampled_at": time.time()}
        try:
            if (marker.get("cleanup_confirmed") is not True or not isinstance(identity, dict)
                    or any(identity.get(name) != key[name] for name in key)):
                raise ValueError("original observation identity does not match retained attempt")
            effect_id, root = self._read_effect(key, deadline)
            fact["effect_id"] = effect_id
            directory = Path(root) / (str(key["attempt"]) + "-" + str(key["fence"]))
            streams = {}
            for stream in ("stdout", "stderr"):
                path = directory / (stream + ".log")
                try:
                    path_text = str(path)
                    if len(path_text) > 768 or len(path_text.encode("utf-8")) > 768:
                        raise ValueError("artifact path exceeds saved fact bound")
                    metadata = path.stat()
                    if not stat.S_ISREG(metadata.st_mode):
                        raise ValueError("script artifact is not a regular file")
                    streams[stream] = {"saved_bytes": metadata.st_size, "path": path_text}
                except Exception as error:
                    streams[stream] = {"unknown_reason": "script_artifact_unavailable",
                                       "error": _text(error)}
            fact["streams"] = streams
        except Exception as error:
            if (is_sqlite_contention(error) or isinstance(error, _ReadDeadline)):
                raise
            fact["streams"] = {name: {"unknown_reason": "script_metadata_unavailable",
                "error": _text(error)} for name in ("stdout", "stderr")}
        if len(json.dumps(fact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 4096:
            # An oversized original identity is never silently truncated or
            # represented as an exact observation identity.
            fact = {"cleanup_confirmed": True, "source": "script_artifact_after_native_cleanup",
                "sampled_at": fact["sampled_at"], "identity_unknown_reason": "identity_exceeds_fact_bound",
                "streams": {name: {"unknown_reason": "saved_fact_exceeds_bound"}
                            for name in ("stdout", "stderr")}}
        return fact

    def _read_effect(self, key: dict[str, Any], deadline: float) -> tuple[str, str]:
        if time.monotonic() >= deadline:
            raise _ReadDeadline("script effect inspection deadline elapsed")
        connection = sqlite3.connect(self._uri, uri=True, timeout=0)
        try:
            connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 100)
            connection.execute("PRAGMA query_only=ON")
            rows = connection.execute(
                "SELECT e.effect_id, CASE WHEN length(CAST(json_extract(e.request_json,'$.output_root') "
                "AS BLOB))<=2048 THEN json_extract(e.request_json,'$.output_root') END "
                "FROM kernel_effects e WHERE e.execution_id=? AND e.name='script.execute' "
                "AND EXISTS (SELECT 1 FROM kernel_effect_events v WHERE v.effect_id=e.effect_id "
                "AND v.execution_id=e.execution_id "
                "AND v.event_type IN ('prepared','reprepared_after_not_applied') "
                "AND json_extract(v.data_json,'$.attempt')=? "
                "AND json_extract(v.data_json,'$.fence')=?) ORDER BY e.effect_id LIMIT 2",
                (key["execution_id"], key["attempt"], key["fence"])).fetchall()
            if time.monotonic() >= deadline:
                raise _ReadDeadline("script effect inspection deadline elapsed")
            if len(rows) != 1:
                raise ValueError("exact original script effect association is missing or ambiguous")
            effect_id, root = rows[0]
            if (type(root) is not str or not root or type(effect_id) is not str
                    or len(effect_id) > 512 or len(effect_id.encode("utf-8")) > 512):
                raise ValueError("original script effect metadata exceeds its bound or is invalid")
            return effect_id, root
        except sqlite3.OperationalError as error:
            if str(error) == "interrupted" and time.monotonic() >= deadline:
                raise _ReadDeadline("script effect inspection deadline elapsed") from error
            raise
        finally:
            connection.close()
