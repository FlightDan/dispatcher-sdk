"""Fail-closed activation of an authenticated local snapshot successor.

Activation is deliberately a same-host handoff.  It proves that every signed
source component is stopped and unchanged, durably retires those source paths,
and only then makes a newly copied successor writable.  It does not implement
remote fencing or protect writers which bypass the SDK connection protocol.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
from types import MappingProxyType
from typing import Any, Mapping
import uuid

from .execution_kernel._registry import Handler
from .maintenance import (
    Lease,
    _retirement_path,
    maintenance_lease,
)
from .storage import inspect_storage
from .storage_snapshots import (
    SnapshotValidationError,
    VerifiedSnapshot,
    _canonical,
    _hash_file,
    _signing_key,
    _sqlite_details,
    verify_snapshot,
)


_ACTIVATION_FORMAT = "dispatcher-sdk-local-snapshot-activation"
_ACTIVATION_VERSION = 1
_RECEIPT = ".sdk-activation.json"
_PENDING = ".sdk-activation-pending.json"
_READ_ONLY_MARKER = ".sdk-snapshot-readonly"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_O_BINARY = getattr(os, "O_BINARY", 0)


class ActivationError(RuntimeError):
    """The local snapshot cannot be activated safely."""


class ActivationConflictError(ActivationError):
    """An operation identity, source, or destination has conflicting content."""


class ActivationPreconditionError(ActivationError):
    """A required deployment, storage, or local fencing proof is absent."""


@dataclass(frozen=True, slots=True)
class ActivationResult:
    """A committed, writable local successor and its durable receipt."""

    path: Path
    receipt_path: Path
    operation_id: str
    components: Mapping[str, Path]
    retired_sources: Mapping[str, Path]


def _validate_operation_id(value: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ValueError("operation_id must be a safe non-empty identifier")
    return value


def _destination(raw: str | os.PathLike[str]) -> Path:
    value = os.fspath(raw)
    if not value:
        raise ValueError("destination path is empty")
    lexical = Path(value).expanduser()
    if ".." in lexical.parts:
        raise ActivationPreconditionError("destination path contains parent traversal")
    target = Path(os.path.abspath(lexical))
    current = Path(target.anchor)
    for part in target.parts[1:-1]:
        current = current / part
        result = current.lstat()
        if stat.S_ISLNK(result.st_mode) or not stat.S_ISDIR(result.st_mode):
            raise ActivationPreconditionError(
                f"destination path traverses an unsafe parent: {current}"
            )
    parent = target.parent
    result = parent.lstat()
    if stat.S_ISLNK(result.st_mode) or not stat.S_ISDIR(result.st_mode):
        raise ActivationPreconditionError("destination parent must be a non-symlink directory")
    return target


def _signed(document: dict[str, Any], key: bytes) -> dict[str, Any]:
    value = dict(document)
    value["authentication"] = {
        "algorithm": "HMAC-SHA256",
        "key_id": hashlib.sha256(key).hexdigest()[:32],
    }
    tag = hmac.new(key, _canonical(value), hashlib.sha256).hexdigest()
    value["authentication"]["tag"] = tag
    return value


def _verify_signed(document: Any, key: bytes, *, label: str) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ActivationConflictError(f"{label} is invalid")
    authentication = document.get("authentication")
    if not isinstance(authentication, dict):
        raise ActivationConflictError(f"{label} authentication is invalid")
    tag = authentication.get("tag")
    unsigned = dict(document)
    unsigned["authentication"] = {
        name: value for name, value in authentication.items() if name != "tag"
    }
    expected = hmac.new(key, _canonical(unsigned), hashlib.sha256).hexdigest()
    if (
        authentication.get("algorithm") != "HMAC-SHA256"
        or authentication.get("key_id") != hashlib.sha256(key).hexdigest()[:32]
        or not isinstance(tag, str)
        or not hmac.compare_digest(tag, expected)
    ):
        raise ActivationConflictError(f"{label} authentication failed")
    return document


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        result = path.lstat()
    except FileNotFoundError as error:
        raise ActivationConflictError(f"{label} is missing: {path}") from error
    if stat.S_ISLNK(result.st_mode) or not stat.S_ISREG(result.st_mode):
        raise ActivationConflictError(f"{label} is unsafe: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ActivationConflictError(f"{label} is invalid: {path}") from error
    if not isinstance(value, dict):
        raise ActivationConflictError(f"{label} is invalid: {path}")
    return value


def _write_new(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.pending")
    descriptor: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_BINARY
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError(f"failed to write {path}")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.link(temporary, path, follow_symlinks=False)
        _sync_directory(path.parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _replace(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.pending")
    _write_new(temporary, payload)
    try:
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _sync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _manifest_digest(snapshot: VerifiedSnapshot) -> str:
    return hashlib.sha256(_canonical(dict(snapshot.manifest))).hexdigest()


def _member(snapshot: VerifiedSnapshot, name: str) -> Mapping[str, Any]:
    for member in snapshot.manifest["members"]:
        if member.get("kind") == "sqlite" and member.get("name") == name:
            return member
    raise ActivationPreconditionError(f"snapshot component metadata is missing: {name}")


def _preflight(snapshot: VerifiedSnapshot, handlers: Mapping[Any, Handler]) -> None:
    if not snapshot.source_components:
        raise ActivationPreconditionError(
            "snapshot predates authenticated source-path binding and cannot be activated"
        )
    if snapshot.blobs:
        raise ActivationPreconditionError(
            "activation does not support caller-owned blob or external resource members"
        )
    kernel_components = 0
    for name, component in snapshot.components.items():
        report = inspect_storage(component, handlers=handlers, check="full")
        if not report["complete"]:
            raise ActivationPreconditionError(f"component inspection was incomplete: {name}")
        recognized = any(
            report.get(field) not in {"absent", "unsupported", None}
            for field in ("kernel_schema", "orchestrator_schema", "inbox_schema")
        )
        if not recognized:
            raise ActivationPreconditionError(f"component is not a supported SDK store: {name}")
        if report.get("sandbox_schema") != "absent" or report.get("sandbox_registry_schema") != "absent":
            raise ActivationPreconditionError(
                "sandbox journals are external resources and cannot be activated safely"
            )
        if report["issues"] or report["checks"]["integrity"] != "ok":
            raise ActivationPreconditionError(
                f"component failed integrity, schema, or deployment preflight: {name}"
            )
        work_store = any(
            report.get(field) not in {"absent", "unsupported", None}
            for field in ("kernel_schema", "orchestrator_schema")
        )
        if work_store and report["checks"]["bindings"] != "checked":
            raise ActivationPreconditionError(
                f"handler deployment could not be checked for component: {name}"
            )
        if report.get("kernel_schema") not in {"absent", "unsupported", None}:
            kernel_components += 1
    if kernel_components != 1:
        raise ActivationPreconditionError("activation requires exactly one execution kernel store")


def _source_matches_snapshot(snapshot: VerifiedSnapshot, name: str, source: Path) -> None:
    try:
        result = source.lstat()
    except FileNotFoundError as error:
        raise ActivationPreconditionError(f"signed source component is missing: {source}") from error
    if stat.S_ISLNK(result.st_mode) or not stat.S_ISREG(result.st_mode):
        raise ActivationPreconditionError(f"signed source component is unsafe: {source}")
    if result.st_nlink != 1:
        raise ActivationPreconditionError("source database has hard-link aliases; ownership cannot be fenced")
    expected = _member(snapshot, name).get("sqlite", {}).get("logical_sha256")
    if not isinstance(expected, str):
        raise ActivationPreconditionError(
            "snapshot predates logical source-state binding and cannot be activated"
        )
    try:
        actual = _sqlite_details(source)["logical_sha256"]
    except (sqlite3.Error, SnapshotValidationError) as error:
        raise ActivationPreconditionError(f"cannot validate signed source component: {source}") from error
    if not hmac.compare_digest(expected, actual):
        raise ActivationPreconditionError(
            f"source changed after the snapshot and cannot be handed off: {source}"
        )


def _retirement_document(
    *, operation_id: str, manifest_digest: str, destination: Path,
    source_name: str, source: Path, key: bytes,
) -> dict[str, Any]:
    return _signed({
        "format": _ACTIVATION_FORMAT,
        "version": _ACTIVATION_VERSION,
        "state": "source-retired",
        "operation_id": operation_id,
        "manifest_sha256": manifest_digest,
        "source_name": source_name,
        "source_path": str(source),
        "successor_path": str(destination),
    }, key)


def _publish_retirement(path: Path, expected: dict[str, Any], key: bytes) -> None:
    payload = _canonical(expected) + b"\n"
    try:
        _write_new(path, payload)
        return
    except FileExistsError:
        existing = _verify_signed(_read_json(path, label="source retirement marker"), key,
                                  label="source retirement marker")
        if existing != expected:
            raise ActivationConflictError(
                "source already identifies a different activation successor"
            )


def _pending_document(
    snapshot: VerifiedSnapshot, destination: Path, operation_id: str, key: bytes
) -> dict[str, Any]:
    return _signed({
        "format": _ACTIVATION_FORMAT,
        "version": _ACTIVATION_VERSION,
        "state": "copying",
        "operation_id": operation_id,
        "manifest_sha256": _manifest_digest(snapshot),
        "destination": str(destination),
        "components": {
            name: path.name for name, path in sorted(snapshot.components.items())
        },
    }, key)


def _reservation_path(destination: Path) -> Path:
    # Keep ownership/commit evidence outside the successor. Losing the entire
    # successor directory must not permit replaying its original snapshot.
    return destination.with_name(f".{destination.name}.sdk-activation.json")


def _matches_receipt(document: Mapping[str, Any], pending: Mapping[str, Any]) -> bool:
    return (
        document.get("format") == _ACTIVATION_FORMAT
        and document.get("version") == _ACTIVATION_VERSION
        and document.get("state") == "activated"
        and document.get("operation_id") == pending["operation_id"]
        and document.get("manifest_sha256") == pending["manifest_sha256"]
        and document.get("destination") == pending["destination"]
        and document.get("components") == pending["components"]
    )


def _reservation(destination: Path, pending: dict[str, Any], key: bytes):
    path = _reservation_path(destination)
    if not os.path.lexists(path):
        return None
    document = _verify_signed(_read_json(path, label="activation reservation"), key,
                              label="activation reservation")
    if document != pending and not _matches_receipt(document, pending):
        raise ActivationConflictError("destination is reserved by a different activation")
    if document["state"] == "activated":
        # Never recreate a committed successor from old input after it has been
        # removed or lost; it may already have performed external operations.
        receipt = _verify_signed(
            _read_json(destination / _RECEIPT, label="committed activation receipt"), key,
            label="committed activation receipt")
        if receipt != document:
            raise ActivationConflictError("committed successor receipt differs from its reservation")
    return document


def _reserve_destination(destination: Path, pending: dict[str, Any], key: bytes) -> None:
    if _reservation(destination, pending, key) is not None:
        return
    try:
        _write_new(_reservation_path(destination), _canonical(pending) + b"\n")
    except FileExistsError:
        _reservation(destination, pending, key)


def _initializing_directory(destination: Path, pending: dict[str, Any], key: bytes) -> bool:
    """Recognize an owned mkdir/marker interruption before pending publication."""
    if _reservation(destination, pending, key) != pending:
        return False
    for entry in destination.iterdir():
        if entry.name == _READ_ONLY_MARKER:
            if entry.is_symlink() or not entry.is_file():
                return False
        elif not (entry.name.startswith("..sdk-") and entry.name.endswith(".pending")
                  and entry.is_file() and not entry.is_symlink()):
            return False
    return True


def _initialize_directory(destination: Path, pending: dict[str, Any]) -> None:
    marker = destination / _READ_ONLY_MARKER
    if not os.path.lexists(marker):
        _write_new(marker, b"Dispatcher SDK activation in progress; writers are disabled.\n")
    _write_new(destination / _PENDING, _canonical(pending) + b"\n")
    _sync_directory(destination)


def _open_or_create_destination(
    destination: Path,
    pending: dict[str, Any],
    key: bytes,
) -> ActivationResult | None:
    try:
        os.mkdir(destination, 0o700)
    except FileExistsError:
        result = destination.lstat()
        if stat.S_ISLNK(result.st_mode) or not stat.S_ISDIR(result.st_mode):
            raise ActivationConflictError("activation destination became unsafe after reservation")
        receipt = destination / _RECEIPT
        if receipt.exists():
            document = _verify_signed(_read_json(receipt, label="activation receipt"), key,
                                      label="activation receipt")
            if _matches_receipt(document, pending):
                components = {
                    name: destination / relative
                    for name, relative in document.get("components", {}).items()
                }
                if any(component.is_symlink() or not component.is_file()
                       for component in components.values()):
                    raise ActivationConflictError("activated destination component is missing")
                return ActivationResult(
                    destination, receipt, pending["operation_id"],
                    MappingProxyType(components), MappingProxyType({}),
                )
            raise ActivationConflictError("destination belongs to another activation")
        if not os.path.lexists(destination / _PENDING) and _initializing_directory(destination, pending, key):
            _initialize_directory(destination, pending)
            return None
        existing = _verify_signed(
            _read_json(destination / _PENDING, label="activation pending record"), key,
            label="activation pending record",
        )
        if existing != pending:
            raise ActivationConflictError("destination has a different incomplete activation")
    else:
        _initialize_directory(destination, pending)
    return None


def _preflight_destination(
    destination: Path, pending: dict[str, Any], key: bytes
) -> None:
    """Reject an unrelated destination before any source is durably retired."""
    _reservation(destination, pending, key)
    try:
        result = destination.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(result.st_mode) or not stat.S_ISDIR(result.st_mode):
        raise ActivationConflictError("activation destination already exists and is unsafe")
    receipt = destination / _RECEIPT
    if receipt.exists():
        document = _verify_signed(
            _read_json(receipt, label="activation receipt"), key,
            label="activation receipt",
        )
        if not _matches_receipt(document, pending):
            raise ActivationConflictError("destination belongs to another activation")
        return
    if not os.path.lexists(destination / _PENDING) and _initializing_directory(destination, pending, key):
        return
    existing = _verify_signed(
        _read_json(destination / _PENDING, label="activation pending record"), key,
        label="activation pending record",
    )
    if existing != pending:
        raise ActivationConflictError("destination has a different incomplete activation")


def _copy_component(source: Path, destination: Path, expected: Mapping[str, Any]) -> None:
    if destination.exists():
        size, digest = _hash_file(destination)
        if size == expected["size"] and hmac.compare_digest(digest, expected["sha256"]):
            return
        raise ActivationConflictError(f"incomplete destination component is inconsistent: {destination}")
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.pending")
    try:
        shutil.copyfile(source, temporary)
        # Windows FlushFileBuffers (os.fsync) requires a writable handle.
        descriptor = os.open(temporary, os.O_RDWR | getattr(os, "O_CLOEXEC", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        size, digest = _hash_file(temporary)
        if size != expected["size"] or not hmac.compare_digest(digest, expected["sha256"]):
            raise ActivationConflictError("restored component changed during activation copy")
        os.link(temporary, destination, follow_symlinks=False)
        _sync_directory(destination.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def activate_restored_snapshot(
    restored: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    signing_key: bytes,
    operation_id: str,
    handlers: Mapping[Any, Handler],
    owner_id: str,
    lease_seconds: float = 30,
    timeout: float = 0,
) -> ActivationResult:
    """Activate a verified local restore after an exclusive source handoff.

    A historical source must still be locally reachable and logically equal to
    the snapshot.  Every SDK participant is excluded before immutable retirement
    markers are published.  Retrying the exact ``operation_id`` resumes a
    fail-closed partial activation; changing its destination or manifest fails.
    """
    key = _signing_key(signing_key)
    operation = _validate_operation_id(operation_id)
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise ValueError("owner_id must be a non-empty string")
    snapshot = verify_snapshot(restored, key)
    _preflight(snapshot, handlers)
    target = _destination(destination)
    if target == snapshot.root or target.is_relative_to(snapshot.root):
        raise ActivationPreconditionError("activation destination cannot be inside the restore")
    digest = _manifest_digest(snapshot)
    pending = _pending_document(snapshot, target, operation, key)
    _preflight_destination(target, pending, key)

    with ExitStack() as stack:
        leases: dict[str, Lease] = {}
        for name, source in sorted(snapshot.source_components.items(), key=lambda item: os.fspath(item[1])):
            leases[name] = stack.enter_context(maintenance_lease(
                source,
                owner_id,
                "activate-restored-snapshot",
                lease_seconds=lease_seconds,
                timeout=timeout,
                _retired_operation_id=operation,
            ))
        identities: set[tuple[int, int]] = set()
        for source in snapshot.source_components.values():
            result = source.lstat()
            identity = (result.st_dev, result.st_ino)
            if identity in identities:
                raise ActivationPreconditionError(
                    "signed source components now alias the same database"
                )
            identities.add(identity)
        for name, source in snapshot.source_components.items():
            leases[name].check(source)
            _source_matches_snapshot(snapshot, name, source)
        # Reservation rejects competing source groups before any retirement,
        # and proves ownership if mkdir is interrupted before its pending file.
        if (not os.path.lexists(_reservation_path(target))
                and any(os.path.lexists(_retirement_path(source))
                        for source in snapshot.source_components.values())):
            raise ActivationConflictError("retired source has lost its activation reservation; refusing replay")
        _reserve_destination(target, pending, key)
        retirements: dict[str, Path] = {}
        for name, source in sorted(snapshot.source_components.items()):
            document = _retirement_document(
                operation_id=operation,
                manifest_digest=digest,
                destination=target,
                source_name=name,
                source=source,
                key=key,
            )
            marker = _retirement_path(source)
            _publish_retirement(marker, document, key)
            retirements[name] = marker
        for name, source in snapshot.source_components.items():
            leases[name].check(source)

        existing = _open_or_create_destination(target, pending, key)
        if existing is not None:
            # A receipt can be durable just before the final gate removal.  In
            # that sole committed-but-gated state, retry completes publication.
            if os.path.lexists(target / _READ_ONLY_MARKER):
                for name, component in existing.components.items():
                    size, component_digest = _hash_file(component)
                    expected = _member(snapshot, name)
                    if size != expected["size"] or not hmac.compare_digest(component_digest, expected["sha256"]):
                        raise ActivationConflictError("gated activation component differs from authenticated snapshot")
                for name, source in snapshot.source_components.items():
                    leases[name].check(source)
                receipt = _verify_signed(_read_json(target / _RECEIPT, label="activation receipt"), key,
                                         label="activation receipt")
                _replace(_reservation_path(target), _canonical(receipt) + b"\n")
                for gate in (target / _PENDING, target / _READ_ONLY_MARKER):
                    try:
                        gate.unlink()
                    except FileNotFoundError:
                        pass
                _sync_directory(target)
            elif _reservation(target, pending, key)["state"] != "activated":
                raise ActivationConflictError("successor write gate was removed before durable activation commit")
            return ActivationResult(
                existing.path, existing.receipt_path, existing.operation_id,
                existing.components, MappingProxyType(dict(snapshot.source_components)),
            )
        components: dict[str, Path] = {}
        for name, source in sorted(snapshot.components.items()):
            for lease_name, lease_source in snapshot.source_components.items():
                leases[lease_name].renew(lease_seconds)
                leases[lease_name].check(lease_source)
            output = target / source.name
            _copy_component(source, output, _member(snapshot, name))
            components[name] = output
        for name, output in components.items():
            expected_logical = _member(snapshot, name)["sqlite"]["logical_sha256"]
            # Activation preserves bytes, lease expiry and retry budgets. Check
            # the copied component's schema and deployment once more before
            # publishing the receipt that enables its writers.
            report = inspect_storage(output, handlers=handlers, check="full")
            if not report["complete"] or report["issues"] or report["checks"]["integrity"] != "ok":
                raise ActivationPreconditionError(f"activated component validation failed: {name}")
            if expected_logical is None:  # defensive shape check
                raise ActivationPreconditionError(f"component lacks a logical digest: {name}")
        for lease_name, lease_source in snapshot.source_components.items():
            leases[lease_name].renew(lease_seconds)
            leases[lease_name].check(lease_source)
        receipt_document = _signed({
            "format": _ACTIVATION_FORMAT,
            "version": _ACTIVATION_VERSION,
            "state": "activated",
            "operation_id": operation,
            "manifest_sha256": digest,
            "destination": str(target),
            "components": {name: path.name for name, path in sorted(components.items())},
            "retired_sources": {name: str(path) for name, path in sorted(snapshot.source_components.items())},
        }, key)
        _replace(target / _RECEIPT, _canonical(receipt_document) + b"\n")
        _replace(_reservation_path(target), _canonical(receipt_document) + b"\n")
        try:
            (target / _PENDING).unlink()
        except FileNotFoundError:
            pass
        (target / _READ_ONLY_MARKER).unlink()
        _sync_directory(target)
        return ActivationResult(
            target,
            target / _RECEIPT,
            operation,
            MappingProxyType(components),
            MappingProxyType(dict(snapshot.source_components)),
        )


__all__ = [
    "ActivationConflictError",
    "ActivationError",
    "ActivationPreconditionError",
    "ActivationResult",
    "activate_restored_snapshot",
]
