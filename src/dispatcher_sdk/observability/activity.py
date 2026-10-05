"""Nonblocking bounded capture with independently scheduled persistence."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
import math
import threading
import time
from typing import Any, Callable, Mapping
import uuid

from .._sqlite_errors import is_sqlite_contention

from .contracts import ObservationIdentity, ObservationOptions, identifier, positive
from .journal import ObservationJournal, _ObservationWriteBudgetExceeded, _bounded_json, _json


class ActivityRecorder:
    """Capture one execution authority without running business control.

    Byte reports never persist or invoke application callbacks. They update
    fixed-size cumulative counters and tails, and optional detail is bounded.
    A short-lived flusher owns SQLite work. Progress confirmation is delegated
    to the injected Kernel capability and cannot be inferred from this cache.
    """

    def __init__(self, journal: ObservationJournal, identity: ObservationIdentity, *,
                 source_id: str | None = None, options: ObservationOptions | None = None,
                 source_scope: str | None = None, metric_coverage: tuple[str, ...] | None = None,
                 progress_confirm: Callable[..., Mapping[str, Any]] | None = None,
                 clock=None, monotonic=None, start: bool = False,
                 bind_current: bool = False,
                 _defer_collector_registration: bool = False) -> None:
        if type(bind_current) is not bool:
            raise ValueError("bind_current must be a bool")
        self.journal = journal
        self.identity = identity
        self.source_id = identifier(source_id or uuid.uuid4().hex, "source_id")
        self.source_scope = None if source_scope is None else identifier(source_scope, "source_scope")
        self.metric_coverage = metric_coverage or (
            "stdout_bytes", "stderr_bytes", "model_requests", "model_text", "model_first_byte_events",
            "model_events", "tool_requests", "tool_responses", "tool_events", "heartbeat", "progress", "phase_events")
        self._collector_incarnation: int | None = None
        self._current_binding_pending = bind_current
        self.options = options or journal.options
        self._confirm = progress_confirm
        self._clock = clock or time.time
        self._monotonic = monotonic or time.monotonic
        self._lock = threading.Lock()
        self._wait_diagnostic_lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._metrics: dict[str, dict[str, Any]] = {}
        self._tails: dict[str, bytes] = {}
        self._events: deque[tuple[dict[str, Any], int]] = deque()
        self._queue_bytes = 0
        self._sequence = 0
        self._gaps = 0
        self._dropped_events = 0
        self._last_error: str | None = None
        self._wait_error: str | None = None
        self._wait_error_at: float | None = None
        self._wait_error_revision = 0
        self._wait_error_persisted_revision = 0
        self._captured_at: float | None = None
        self._persisted_at: float | None = None
        self._collected_at: float | None = None
        self._progress_receipt: dict[str, Any] | None = None
        self._applied_progress_revision = 0
        self._started_monotonic = self._monotonic()
        self._handler_entered_monotonic: float | None = None
        self._last_progress_monotonic: float | None = None
        self._closed = False
        self._process_observer: Any = None
        self._close_complete = threading.Event()
        self._close_result: dict[str, Any] | None = None
        self._close_deadline: float | None = None
        # Runtime owns one recorder per exact lease and scope. Its first owned
        # flush can register after binding without delaying handler entry.
        # Public construction keeps registration order even if flushes reorder.
        if self.source_scope is not None and not _defer_collector_registration:
            try:
                self._collector_incarnation = self.journal.register_collector(identity, self.source_id,
                    source_scope=self.source_scope, metric_coverage=self.metric_coverage)
            except Exception as error:
                self._last_error = f"{type(error).__name__}: {error}"
        if start:
            self.start()

    def _increment(self, metric: str, count: int, captured_at: float) -> None:
        if not math.isfinite(captured_at):
            raise ValueError("capture time must be finite")
        if self._captured_at is not None and captured_at < self._captured_at:
            self._gaps += 1
        value = self._metrics.setdefault(metric, {"count": 0, "first_at": None, "last_at": None})
        first_stream_bytes = (metric in ("stdout_bytes", "stderr_bytes")
                              and value["count"] == 0 and count > 0)
        value["count"] += count
        if value["first_at"] is None:
            value["first_at"] = captured_at
        value["last_at"] = captured_at
        self._captured_at = captured_at
        if first_stream_bytes:
            # One early cumulative batch keeps a short-lived stream from
            # waiting for the periodic tick. Later chunks remain coalesced;
            # capture never performs SQLite work or flushes per chunk.
            self._wake.set()

    def _wait_failure(self, error: str, captured_at: float, *, gap: bool = True) -> None:
        bounded_error = error.encode("utf-8")[:512].decode("utf-8", errors="ignore")
        with self._wait_diagnostic_lock:
            if gap:
                self._gaps += 1
            self._wait_error = bounded_error
            self._wait_error_at = captured_at if math.isfinite(captured_at) else 0.0
            self._wait_error_revision += 1

    def _queue_wait(self, kind: str, original: dict[str, Any], captured_at: float) -> bool:
        if self._closed:
            self._wait_failure("wait recorder closed", captured_at)
            return False
        if not self._lock.acquire(blocking=False):
            self._wait_failure("wait capture busy", captured_at)
            return False
        try:
            if self._closed:
                self._wait_failure("wait recorder closed", captured_at)
                return False
            return self._enqueue(kind, original, captured_at)
        except Exception as error:
            self._wait_failure(f"{type(error).__name__}: {error}", captured_at)
            return False
        finally:
            self._lock.release()

    def _enqueue(self, kind: str, details: dict[str, Any], captured_at: float) -> bool:
        event = {"kind": kind, "captured_at": captured_at, "details": details}
        encoded = _bounded_json(event, min(4096, self.options.queue_bytes, self.options.batch_bytes)).encode("utf-8")
        size = len(encoded)
        if size > min(4096, self.options.queue_bytes, self.options.batch_bytes):
            self._dropped_events += 1
            self._gaps += 1
            return False
        while self._events and (len(self._events) >= self.options.queue_items or
                                self._queue_bytes + size > self.options.queue_bytes):
            dropped, removed = self._events.popleft()
            self._queue_bytes -= removed
            self._dropped_events += 1
            self._gaps += 1
            if dropped["kind"] in ("wait_begin", "wait_end"):
                self._wait_failure("wait observation dropped by bounded queue", captured_at, gap=False)
        self._events.append((event, size))
        self._queue_bytes += size
        return True

    def _capture(self, metric: str, *, count: int = 1, kind: str | None = None,
                 details: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._closed:
            return {"state": "degraded", "reason": "recorder_closed"}
        if not self._lock.acquire(blocking=False):
            self._gaps += 1
            return {"state": "degraded", "reason": "capture_busy"}
        try:
            now = float(self._clock())
            self._increment(metric, count, now)
            if kind is not None:
                self._enqueue(kind, details or {}, now)
            return {"state": "captured", "captured_at": now, "persisted": False}
        except Exception as error:
            self._last_error = f"{type(error).__name__}: {error}"
            self._gaps += 1
            return {"state": "degraded", "reason": "capture_error"}
        finally:
            self._lock.release()

    def report_bytes(self, stream: str, chunk: bytes, *, retain_tail: bool = True) -> dict[str, Any]:
        """Observe an already received raw chunk; no newline or decode required."""
        if stream not in ("stdout", "stderr") or not isinstance(chunk, (bytes, bytearray, memoryview)):
            return {"state": "degraded", "reason": "invalid_byte_report"}
        if not chunk:
            return {"state": "ignored", "reason": "empty_chunk"}
        if self._closed:
            return {"state": "degraded", "reason": "recorder_closed"}
        if not self._lock.acquire(blocking=False):
            self._gaps += 1
            return {"state": "degraded", "reason": "capture_busy"}
        try:
            now = float(self._clock())
            raw = memoryview(chunk).cast("B")
            self._increment(stream + "_bytes", raw.nbytes, now)
            if retain_tail:
                tail = bytes(raw[-self.options.tail_bytes:])
                self._tails[stream] = (self._tails.get(stream, b"") + tail)[-self.options.tail_bytes:]
            return {"state": "captured", "captured_at": now, "persisted": False}
        except Exception as error:
            self._last_error = f"{type(error).__name__}: {error}"
            self._gaps += 1
            return {"state": "degraded", "reason": "capture_error"}
        finally:
            self._lock.release()

    def enable_stream(self, stream: str) -> dict[str, Any]:
        """Declare that a stream drain is installed, distinguishing zero/unknown."""
        if stream not in ("stdout", "stderr"):
            return {"state": "degraded", "reason": "invalid_stream"}
        if not self._lock.acquire(blocking=False):
            self._gaps += 1
            return {"state": "degraded", "reason": "capture_busy"}
        try:
            self._metrics.setdefault(stream + "_bytes", {"count": 0, "first_at": None, "last_at": None})
            return {"state": "captured", "persisted": False}
        finally:
            self._lock.release()

    def report_byte_count(self, stream: str, byte_count: int, *, source: str | None = None) -> dict[str, Any]:
        """Count an adapter's observed raw bytes without retaining private contents."""
        if stream not in ("stdout", "stderr") or type(byte_count) is not int or byte_count < 0:
            return {"state": "degraded", "reason": "invalid_byte_count"}
        return self._capture(stream+"_bytes", count=byte_count)

    def model(self, kind: str = "event") -> dict[str, Any]:
        if type(kind) is not str or len(kind) > 128:
            return {"state": "degraded", "reason": "invalid_model_kind"}
        metrics = {"request": "model_requests", "text": "model_text", "first_text": "model_text",
                   "first_byte": "model_first_byte_events"}
        return self._capture(metrics.get(kind, "model_events"), kind="model", details={"kind": kind})

    report_model = model

    def tool(self, kind: str = "activity") -> dict[str, Any]:
        if type(kind) is not str or len(kind) > 128:
            return {"state": "degraded", "reason": "invalid_tool_kind"}
        metrics = {"request": "tool_requests", "response": "tool_responses"}
        return self._capture(metrics.get(kind, "tool_events"), kind="tool", details={"kind": kind})

    report_tool = tool

    def observe_process(self, process: Any, *, role: str = "agent", process_id: str | None = None):
        """Observe an actual child handle independently of its stdout drain."""
        from .processes import ProcessObserver
        with self._lock:
            if self._process_observer is None:
                self._process_observer = ProcessObserver(self, start=not self._closed)
                if self._closed:
                    self._process_observer._stop.set()
            observer = self._process_observer
        return observer.observe_process(process, role=role, process_id=process_id)

    def wait(self, reason: str, *, target: Any = None, deadline_at: float | None = None,
             resources: Mapping[str, Any] | None = None):
        """Queue original wait facts without depending on SQLite admission."""
        from contextlib import contextmanager
        import json

        @contextmanager
        def waiting():
            wait_id = uuid.uuid4().hex
            started_at = 0.0
            original = None
            try:
                started_at = float(self._clock())
                if not math.isfinite(started_at):
                    raise ValueError("wait capture time must be finite")
                value = {"wait_id": wait_id, "started_at": started_at,
                    "wait": {"reason": reason, "target": target, "deadline_at": deadline_at,
                             "resources": dict(resources or {})}}
                # Snapshot and byte-bound caller-owned containers before
                # either event enters the shared bounded telemetry queue.
                candidate = json.loads(_bounded_json(value, min(3072, self.options.queue_bytes,
                                                                self.options.batch_bytes)))
                _bounded_json({**candidate["wait"], "_collector_source_id": self.source_id}, 4096)
                original = candidate
                captured = self._queue_wait("wait_begin", original, started_at)
            except Exception as error:
                self._wait_failure(f"{type(error).__name__}: {error}", started_at)
                captured = False
            try:
                yield {"wait_id": wait_id, "state": "captured" if captured else "unknown",
                       "persisted": False}
            finally:
                if original is not None:
                    try:
                        ended_at = float(self._clock())
                        if not math.isfinite(ended_at):
                            raise ValueError("wait capture time must be finite")
                        self._queue_wait("wait_end", original, ended_at)
                    except Exception as error:
                        self._wait_failure(f"{type(error).__name__}: {error}", started_at)
        return waiting()

    def heartbeat(self) -> dict[str, Any]:
        return self._capture("heartbeat")

    def phase(self, phase: str, *, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if type(phase) is not str or not phase.strip() or len(phase) > 128:
            return {"state": "degraded", "reason": "invalid_phase"}
        try:
            if details is not None and len(details) > 64:
                raise ValueError("too many phase detail fields")
            payload = {"phase": phase, "details": dict(details or {})}
            _bounded_json(payload, min(4096, self.options.queue_bytes, self.options.batch_bytes))
        except Exception as error:
            self._last_error = f"{type(error).__name__}: {error}"
            self._gaps += 1
            return {"state": "degraded", "reason": "invalid_phase_details"}
        receipt = self._capture("phase_events", kind="phase", details=payload)
        if phase == "handler_entered" and receipt["state"] == "captured":
            with self._lock:
                if self._handler_entered_monotonic is None:
                    self._handler_entered_monotonic = self._monotonic()
        return receipt

    def progress(self, key: str, *, details: Mapping[str, Any] | None = None,
                 timeout: float | None = None) -> dict[str, Any]:
        """Return confirmed only when the injected authority committed progress.

        The callable receives (key, details=<mapping>, timeout=<seconds>). It
        returns state='confirmed', revision=<int>, advanced=<bool>. Replaying
        the same milestone must return advanced=False. Telemetry persistence
        after confirmation does not revoke that authoritative receipt.
        """
        identifier(key, "progress key")
        duration = self.options.write_timeout if timeout is None else positive(timeout, "timeout")
        if self._closed:
            return {"state": "unknown", "reason": "recorder_closed"}
        if self._confirm is None:
            return {"state": "unknown", "reason": "progress_authority_unavailable"}
        try:
            receipt = dict(self._confirm(key, details=dict(details or {}), timeout=duration))
        except Exception as error:
            self._last_error = f"{type(error).__name__}: {error}"
            return {"state": "unknown", "reason": "progress_confirmation_failed", "error": self._last_error}
        if receipt.get("state") != "confirmed":
            return receipt
        revision = receipt.get("revision")
        if type(revision) is not int or revision < 0 or type(receipt.get("advanced")) is not bool:
            return {"state": "unknown", "reason": "invalid_progress_receipt"}
        with self._lock:
            previous_revision = None if self._progress_receipt is None else self._progress_receipt["revision"]
            if previous_revision is None or revision >= previous_revision:
                self._progress_receipt = receipt
            if receipt["advanced"] and revision > self._applied_progress_revision:
                try:
                    now = float(self._clock())
                    progress_monotonic = self._monotonic()
                    self._increment("progress", 1, now)
                    self._last_progress_monotonic = progress_monotonic
                    self._applied_progress_revision = revision
                    self._enqueue("progress", {"key": key, "revision": revision}, now)
                except Exception as error:
                    self._last_error = f"{type(error).__name__}: {error}"
                    self._gaps += 1
                    receipt = {**receipt, "observation_state": "degraded", "observation_error": self._last_error}
        return receipt

    def _prepare_batch(self) -> dict[str, Any]:
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
            metrics = deepcopy(self._metrics)
            tails = dict(self._tails)
            # Sampling a quiet recorder is still a successful collection.
            # Metric last_at retains the separate last activity instant.
            captured_at = float(self._clock())
            gaps = self._gaps
            base_size = len(_json(metrics).encode("utf-8")) + sum((len(value) + 2) // 3 * 4 for value in tails.values()) + 256
            selected = []
            consumed_bytes = 0
            with self._wait_diagnostic_lock:
                gaps = self._gaps
                wait_error_revision = self._wait_error_revision
                diagnostic = {"kind": "wait_coverage", "captured_at": self._wait_error_at,
                    "details": {"error": self._wait_error, "collection_gaps": self._gaps}}
            if wait_error_revision > self._wait_error_persisted_revision:
                diagnostic_size = len(_json(diagnostic).encode("utf-8"))
                if base_size + diagnostic_size <= self.options.batch_bytes:
                    selected.append(diagnostic)
                    consumed_bytes += diagnostic_size
            for event, size in self._events:
                if len(selected) >= self.options.batch_summaries or base_size + consumed_bytes + size > self.options.batch_bytes:
                    break
                selected.append(event)
                consumed_bytes += size
            # A configured small batch can still keep its cumulative
            # summary by truncating optional tails, never its counters.
            tail_budget = max(0, (self.options.batch_bytes - len(_json(metrics).encode("utf-8")) - consumed_bytes - 256) * 3 // 4)
            if sum(map(len, tails.values())) > tail_budget:
                each = tail_budget // max(1, len(tails))
                tails = {name: value[-each:] if each else b"" for name, value in tails.items()}
        return {"sequence": sequence, "metrics": metrics, "tails": tails, "captured_at": captured_at,
                "gaps": gaps, "selected": selected, "wait_error_revision": wait_error_revision}

    @staticmethod
    def _transient_storage_error(error: Exception) -> bool:
        return (is_sqlite_contention(error)
                or (isinstance(error, _ObservationWriteBudgetExceeded) and error.rollback_confirmed))

    def flush(self) -> dict[str, Any]:
        """Persist one finite batch; failures keep bounded detail for replay."""
        return self._flush()

    def _flush(self, batch_holder: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not self._flush_lock.acquire(blocking=False):
            return {"state": "pending", "reason": "flush_busy", "retryable": True}
        try:
            batch = batch_holder[0] if batch_holder else self._prepare_batch()
            if batch_holder is not None and not batch_holder:
                batch_holder.append(batch)
            sequence, metrics, tails = batch["sequence"], batch["metrics"], batch["tails"]
            captured_at, gaps, selected = batch["captured_at"], batch["gaps"], batch["selected"]
            try:
                if self._current_binding_pending:
                    self.journal.bind_current(self.identity)
                    self._current_binding_pending = False
                if self.source_scope is not None and self._collector_incarnation is None:
                    self._collector_incarnation = self.journal.register_collector(
                        self.identity, self.source_id, source_scope=self.source_scope,
                        metric_coverage=self.metric_coverage)
                self.journal.write_batch(self.identity, source_id=self.source_id, sequence=sequence,
                                         metrics=metrics, tails=tails, captured_at=captured_at,
                                         gaps=gaps, events=tuple(selected), source_scope=self.source_scope,
                                         collector_incarnation=self._collector_incarnation)
            except Exception as error:
                with self._lock:
                    self._last_error = f"{type(error).__name__}: {error}"
                    if any(event["kind"] in ("wait_begin", "wait_end") for event in selected):
                        self._wait_failure(self._last_error, captured_at)
                return {"state": "degraded", "reason": "persistence_failed", "error": self._last_error,
                        "retryable": self._transient_storage_error(error)}
            with self._lock:
                # Capture may overflow/drop selected events while SQLite is
                # busy; remove only the actual queued object we persisted.
                selected_ids = {id(event) for event in selected}
                retained = deque()
                retained_bytes = 0
                for event, size in self._events:
                    if id(event) not in selected_ids:
                        retained.append((event, size))
                        retained_bytes += size
                self._events = retained
                self._queue_bytes = retained_bytes
                self._persisted_at = float(self._clock())
                self._collected_at = captured_at
                if any(event["kind"] == "wait_coverage" for event in selected):
                    self._wait_error_persisted_revision = batch["wait_error_revision"]
                self._last_error = None
            return {"state": "persisted", "sequence": sequence, "persisted_at": self._persisted_at}
        finally:
            self._flush_lock.release()

    def snapshot(self, *, persisted_only: bool = False) -> dict[str, Any]:
        if persisted_only:
            return self.journal.inspect(self.identity.execution_id, attempt=self.identity.attempt, fence=self.identity.fence)
        with self._lock:
            now = float(self._clock())
            baseline = self._handler_entered_monotonic if self._handler_entered_monotonic is not None else self._started_monotonic
            origin = self._last_progress_monotonic if self._last_progress_monotonic is not None else baseline
            output = {}
            for stream in ("stdout", "stderr"):
                metric = self._metrics.get(stream + "_bytes")
                missing = None if metric is None else metric["first_at"] is None
                output[stream] = {"known": metric is not None, "first_missing": missing,
                                  "wait_seconds": max(0.0, self._monotonic() - baseline) if missing else None}
            return {"identity": self.identity.to_dict(), "source_id": self.source_id,
                    "source_scope": self.source_scope, "collector_incarnation": self._collector_incarnation, "view": "local",
                    "observed_at": now, "captured_at": self._captured_at, "collected_at": self._collected_at,
                    "persisted_at": self._persisted_at,
                    "metrics": deepcopy(self._metrics), "tails": dict(self._tails),
                    "output": output, "timing_baseline": "handler_entered" if self._handler_entered_monotonic is not None else "collector_started",
                    "progress_receipt": deepcopy(self._progress_receipt),
                    "no_progress_seconds": max(0.0, self._monotonic() - origin),
                    "queued_items": len(self._events), "queued_bytes": self._queue_bytes,
                    "dropped_events": self._dropped_events, "collection_gaps": self._gaps,
                    "complete": self._gaps == 0 and self._last_error is None and self._wait_error is None,
                    "error": self._last_error or self._wait_error, "wait_error": self._wait_error,
                    "closed": self._closed}

    def start(self) -> ActivityRecorder:
        with self._lock:
            if self._closed:
                raise RuntimeError("recorder is closed")
            if self._thread is not None:
                return self
            self._thread = threading.Thread(target=self._run, name="dispatcher-observation-flush", daemon=True)
            self._thread.start()
        return self

    def _run(self) -> None:
        with self.journal._flush_anchor():
            while True:
                self._wake.wait(self.options.flush_interval)
                self._wake.clear()
                if self._stop.is_set():
                    if self._close_deadline is not None:
                        self._finish_close(self._close_deadline)
                    return
                self.flush()

    def close(self, *, timeout: float = 1.0) -> dict[str, Any]:
        """Stop collection and persist within one total caller wait budget.

        An in-flight journal operation may complete after that budget. Such a
        close returns pending with final_flush_persisted=False until the close
        worker has confirmed its receipt; subsequent calls reuse that worker.
        """
        duration = positive(timeout, "timeout")
        deadline = time.monotonic() + duration
        with self._lock:
            closing = self._closed
            self._closed = True
            # A delayed flusher may spend the entire original close deadline
            # in a journal operation. Collection must still stop immediately.
            if self._process_observer is not None:
                self._process_observer._stop.set()
                self._process_observer._wake.set()
            if not closing:
                self._close_deadline = deadline
                self._stop.set()
                self._wake.set()
                if self._thread is None or not self._thread.is_alive():
                    self._thread = threading.Thread(target=self._run, name="dispatcher-observation-flush", daemon=True)
                    self._thread.start()
        self._close_complete.wait(max(0.0, deadline - time.monotonic()))
        # A persisted receipt precedes the flusher's physical anchor release.
        # Use only this caller's remaining allowance to finish ordinary close;
        # unresolved workers keep their existing Runtime ownership.
        worker = self._thread
        if worker is not None and worker is not threading.current_thread():
            worker.join(max(0.0, deadline - time.monotonic()))
        return self._close_result or {"state": "pending", "reason": "close_in_progress",
                                      "timed_out": True, "final_flush_persisted": False,
                                      "source_closed": False}

    def _owned_workers_alive(self) -> bool:
        observer = self._process_observer
        workers = (self._thread, None if observer is None else observer._thread)
        return any(worker is not None and worker.is_alive() for worker in workers)

    def _join_owned_workers(self, deadline: float) -> dict[str, Any]:
        """Drain lifetime ownership without changing the telemetry receipt.

        Runtime storage must outlive an operation which exceeded recorder
        close's caller wait. Joining does not restart a flush or renew that
        operation's original deadline, and cannot confirm lost telemetry.
        """
        observer = self._process_observer
        workers = (self._thread, None if observer is None else observer._thread)
        for worker in workers:
            if worker is not None and worker is not threading.current_thread():
                worker.join(max(0.0, deadline - time.monotonic()))
        flusher_alive = self._thread is not None and self._thread.is_alive()
        observer_alive = observer is not None and observer._thread is not None and observer._thread.is_alive()
        return {"identity": self.identity.to_dict(), "source_id": self.source_id,
                "state": "pending" if flusher_alive or observer_alive else "closed",
                "flusher_alive": flusher_alive, "process_observer_alive": observer_alive}

    def _finish_close(self, deadline: float) -> None:
        result: dict[str, Any] = {"state": "pending", "reason": "close_deadline",
                                  "final_flush_persisted": False, "source_closed": False}
        observer_result = None
        remaining = lambda: max(0.0, deadline - time.monotonic())
        try:
            # Reserve budget for the final cumulative summary even when a
            # process collector or previous flusher is completing a write.
            if self._process_observer is not None and remaining() > 0:
                observer_result = self._process_observer.close(timeout=min(.25, remaining() / 4))
            if self._thread is not None and self._thread is not threading.current_thread() and remaining() > 0:
                self._thread.join(min(remaining() / 4, self.options.write_timeout + .01))
            batch_holder: list[dict[str, Any]] = []
            while remaining() > 0:
                result = {**self._flush(batch_holder), "final_flush_persisted": False, "source_closed": False}
                if result["state"] == "persisted":
                    result["final_flush_persisted"] = True
                    with self._lock:
                        unfinished = bool(self._events) or self._wait_error_revision > self._wait_error_persisted_revision
                    if unfinished:
                        result.update(state="pending", reason="remaining_observations", final_flush_persisted=False)
                        batch_holder.clear()
                        continue
                    self._close_result = {**result, "state": "pending", "reason": "source_close_pending"}
                    break
                if not result.get("retryable"):
                    break
                threading.Event().wait(min(.005, remaining()))
            if result["final_flush_persisted"]:
                while remaining() > 0:
                    try:
                        self.journal.close_source(self.identity, self.source_id)
                        result.update(state="persisted", source_closed=True)
                        result.pop("reason", None)
                        result.pop("error", None)
                        break
                    except Exception as error:
                        result.update(state="degraded", reason="source_close_failed", error=str(error))
                        if not self._transient_storage_error(error):
                            break
                        threading.Event().wait(min(.005, remaining()))
                if not result["source_closed"] and result["state"] == "persisted":
                    result.update(state="pending", reason="source_close_pending")
            if remaining() <= 0 and not result["source_closed"]:
                result["timed_out"] = True
            if self._thread is not None and self._thread is not threading.current_thread() and self._thread.is_alive():
                result.update(state="pending", reason="flusher_still_active")
            if observer_result is not None:
                result["process_observer"] = observer_result
        except Exception as error:
            result.update(state="degraded", reason="close_failed", error=f"{type(error).__name__}: {error}")
        finally:
            self._close_result = result
            self._close_complete.set()


__all__ = ["ActivityRecorder"]
