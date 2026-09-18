"""Cross-process maintenance exclusion for one stable database path.

This module is deliberately a low-level primitive.  A normal storage user
holds :func:`storage_participant`; maintenance holds
:func:`maintenance_lease`.  It does not stop workers, discover related
stores, or make writers which bypass this protocol safe.

The primary lock name has a permanent hard-link anchor so deleting or replacing
one name fails closed.  A hostile filesystem owner who removes *all*
coordination names can still bypass this process-local protocol.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import errno
import json
import math
import os
from pathlib import Path
import stat
import threading
import time
from typing import Iterator
import uuid


_FORMAT_VERSION = 1
_LOCK_SUFFIX = ".sdk-lock"
_LOCK_ANCHOR_SUFFIX = ".sdk-lock-anchor"
_METADATA_SUFFIX = ".sdk-maintenance.json"
_RETIRED_SUFFIX = ".sdk-retired.json"
_SNAPSHOT_READ_ONLY_MARKER = ".sdk-snapshot-readonly"
_MAX_METADATA_BYTES = 64 * 1024
_RETRY_INTERVAL_SECONDS = 0.01
_O_BINARY = getattr(os, "O_BINARY", 0)


class MaintenanceError(RuntimeError):
    """Base class for maintenance coordination failures."""


class MaintenanceBusyError(MaintenanceError):
    """The requested shared or exclusive lock could not be acquired."""


class InvalidLeaseError(MaintenanceError):
    """A lease is expired, foreign, inactive, or otherwise unusable."""


class MaintenanceMetadataError(MaintenanceError):
    """The durable maintenance descriptor is invalid or unsafe."""


class SnapshotReadOnlyError(MaintenanceError):
    """A snapshot or restored artifact has not been explicitly activated."""


class StorageRetiredError(MaintenanceError):
    """The local store was durably fenced in favor of a restored successor."""


class UnsupportedLockingError(MaintenanceError):
    """The platform cannot provide the required cross-process locks."""


@dataclass(frozen=True, slots=True)
class LeaseInfo:
    """Read-only public representation of a persisted maintenance lease."""

    id: str
    path: Path
    owner: str
    purpose: str
    expires_at: float
    fence: int
    pid: int

    @property
    def owner_id(self) -> str:
        """Alias retained for callers which use the acquisition argument name."""
        return self.owner

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at


@dataclass(frozen=True, slots=True)
class MaintenanceInspection:
    """The durable descriptor, if one has been created for this database."""

    path: Path
    fence: int
    lease: LeaseInfo | None


@dataclass(slots=True)
class _LeaseState:
    path: Path
    lock_path: Path
    metadata_path: Path
    descriptor: int
    process_id: int
    lease_id: str
    owner: str
    purpose: str
    fence: int
    duration: float
    expires_at: float
    monotonic_deadline: float
    active: bool = True


class Lease:
    """An immutable maintenance authority backed by a held exclusive lock.

    Public identity fields cannot be changed.  ``renew`` updates only the
    private lifetime state and the durable descriptor, so existing references
    observe the new ``expires_at`` value.  Expiry forbids starting another
    phase or publication through ``check``; it does not release the physical
    lock, so an atomic commit already in progress may finish before context
    exit.  Callers must check immediately before each new destructive phase.
    """

    __slots__ = ("_state",)

    def __init__(self, state: _LeaseState) -> None:
        object.__setattr__(self, "_state", state)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Lease instances are immutable")

    @property
    def id(self) -> str:
        return self._state.lease_id

    @property
    def lease_id(self) -> str:
        return self._state.lease_id

    @property
    def path(self) -> Path:
        return self._state.path

    @property
    def owner(self) -> str:
        return self._state.owner

    @property
    def owner_id(self) -> str:
        return self._state.owner

    @property
    def purpose(self) -> str:
        return self._state.purpose

    @property
    def expires_at(self) -> float:
        return self._state.expires_at

    @property
    def fence(self) -> int:
        return self._state.fence

    def check(self, path: str | os.PathLike[str]) -> Lease:
        """Validate path, process ownership, lifetime, and durable identity."""
        state = self._state
        requested, _, _ = _coordination_paths(path)
        if requested != state.path:
            raise InvalidLeaseError("maintenance lease belongs to another database path")
        _assert_not_snapshot_artifact(requested)
        if os.getpid() != state.process_id:
            raise InvalidLeaseError("maintenance lease belongs to another process")
        if not state.active:
            raise InvalidLeaseError("maintenance lease is no longer active")
        _validate_held_lock(state)
        if time.monotonic() >= state.monotonic_deadline or time.time() >= state.expires_at:
            raise InvalidLeaseError("maintenance lease has expired")
        inspection = _read_inspection(state.path, state.metadata_path)
        if inspection is None or inspection.lease is None:
            raise InvalidLeaseError("maintenance lease is absent from its durable descriptor")
        persisted = inspection.lease
        if persisted.id != state.lease_id or persisted.fence != state.fence:
            raise InvalidLeaseError("maintenance lease durable identity has changed")
        return self

    def renew(self, lease_seconds: float | None = None) -> Lease:
        """Extend this lease while its exclusive OS lock is still held."""
        state = self._state
        self.check(state.path)
        duration = state.duration if lease_seconds is None else _positive_seconds(
            lease_seconds, "lease_seconds"
        )
        now_wall = time.time()
        now_monotonic = time.monotonic()
        expires_at = now_wall + duration
        descriptor = _descriptor_document(
            state.path,
            state.fence,
            LeaseInfo(
                id=state.lease_id,
                path=state.path,
                owner=state.owner,
                purpose=state.purpose,
                expires_at=expires_at,
                fence=state.fence,
                pid=state.process_id,
            ),
        )
        _publish_metadata(state.metadata_path, descriptor)
        state.duration = duration
        state.expires_at = expires_at
        state.monotonic_deadline = now_monotonic + duration
        return self

    def __repr__(self) -> str:
        return (
            f"Lease(id={self.id!r}, path={str(self.path)!r}, owner={self.owner!r}, "
            f"purpose={self.purpose!r}, expires_at={self.expires_at!r}, "
            f"fence={self.fence!r})"
        )


def _coordination_paths(
    database_path: str | os.PathLike[str],
) -> tuple[Path, Path, Path]:
    supplied = Path(database_path)
    if not supplied.name:
        raise ValueError("database_path must name a file")
    database = supplied.expanduser().resolve(strict=False)
    lock_path = database.with_name(database.name + _LOCK_SUFFIX)
    metadata_path = database.with_name(database.name + _METADATA_SUFFIX)
    return database, lock_path, metadata_path


def _positive_seconds(value: float, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite positive number") from error
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return result


def _timeout_seconds(value: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("timeout must be a finite non-negative number") from error
    if not math.isfinite(result) or result < 0:
        raise ValueError("timeout must be a finite non-negative number")
    return result


def _safe_existing_regular(path: Path, *, label: str) -> os.stat_result | None:
    try:
        result = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(result.st_mode):
        raise MaintenanceMetadataError(f"refusing symbolic-link {label}: {path}")
    if not stat.S_ISREG(result.st_mode):
        raise MaintenanceMetadataError(f"{label} is not a regular file: {path}")
    return result


def _open_lock_file(path: Path) -> int:
    anchor = path.with_name(path.name.removesuffix(_LOCK_SUFFIX) + _LOCK_ANCHOR_SUFFIX)
    _ensure_lock_anchor(path, anchor)
    flags = os.O_RDWR
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.EMLINK):
            raise MaintenanceMetadataError(
                f"refusing symbolic-link maintenance lock path: {path}"
            ) from error
        raise
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise MaintenanceMetadataError(f"maintenance lock path is not a regular file: {path}")
        current = _safe_existing_regular(path, label="maintenance lock path")
        anchored = _safe_existing_regular(anchor, label="maintenance lock anchor")
        opened_identity = (opened.st_dev, opened.st_ino)
        if (
            current is None
            or anchored is None
            or opened_identity != (current.st_dev, current.st_ino)
            or opened_identity != (anchored.st_dev, anchored.st_ino)
        ):
            raise MaintenanceMetadataError("maintenance lock path changed while it was opened")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _ensure_lock_anchor(path: Path, anchor: Path) -> None:
    """Make both permanent names refer to one inode, or fail closed.

    The anchor lets a missing primary name be reconstructed without abandoning
    locks held on its inode.  Replacing either surviving name with another
    inode is treated as coordination corruption, never as lock initialization.
    """
    for _ in range(8):
        primary = _safe_existing_regular(path, label="maintenance lock path")
        anchored = _safe_existing_regular(anchor, label="maintenance lock anchor")
        if primary is not None and anchored is not None:
            if (primary.st_dev, primary.st_ino) != (anchored.st_dev, anchored.st_ino):
                raise MaintenanceMetadataError(
                    "maintenance lock path and permanent anchor refer to different files"
                )
            return
        if primary is None and anchored is None:
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(path, flags, 0o600)
            except FileExistsError:
                continue
            except OSError as error:
                if error.errno in (errno.ELOOP, errno.EMLINK):
                    raise MaintenanceMetadataError(
                        f"refusing symbolic-link maintenance lock path: {path}"
                    ) from error
                raise
            else:
                os.close(descriptor)
                _sync_directory(path.parent)
                continue
        source, destination = (anchor, path) if primary is None else (path, anchor)
        try:
            os.link(source, destination, follow_symlinks=False)
        except FileExistsError:
            continue
        except OSError as error:
            raise UnsupportedLockingError(
                "maintenance coordination requires same-filesystem hard-link support"
            ) from error
        _sync_directory(path.parent)
    raise MaintenanceMetadataError("maintenance lock names changed repeatedly during initialization")


def _validate_lock_descriptor(descriptor: int, lock_path: Path) -> None:
    try:
        opened = os.fstat(descriptor)
    except OSError as error:
        raise MaintenanceMetadataError("maintenance lock handle is no longer open") from error
    anchor = lock_path.with_name(
        lock_path.name.removesuffix(_LOCK_SUFFIX) + _LOCK_ANCHOR_SUFFIX
    )
    primary = _safe_existing_regular(lock_path, label="maintenance lock path")
    anchored = _safe_existing_regular(anchor, label="maintenance lock anchor")
    identity = (opened.st_dev, opened.st_ino)
    if (
        primary is None
        or anchored is None
        or identity != (primary.st_dev, primary.st_ino)
        or identity != (anchored.st_dev, anchored.st_ino)
    ):
        raise MaintenanceMetadataError("maintenance lock names no longer identify the held lock")


def _validate_held_lock(state: _LeaseState) -> None:
    try:
        _validate_lock_descriptor(state.descriptor, state.lock_path)
    except MaintenanceMetadataError as error:
        raise InvalidLeaseError("maintenance lock names are unsafe or no longer held") from error


if os.name == "posix":
    import fcntl

    def _try_lock(descriptor: int, *, exclusive: bool) -> bool:
        operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN):
                return False
            raise
        return True

    def _unlock(descriptor: int) -> None:
        fcntl.flock(descriptor, fcntl.LOCK_UN)

elif os.name == "nt":  # pragma: no cover - exercised by Windows CI
    import ctypes
    from ctypes import wintypes
    import msvcrt

    class _OVERLAPPED(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_void_p),
            ("InternalHigh", ctypes.c_void_p),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _lock_file_ex = _kernel32.LockFileEx
    _lock_file_ex.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_OVERLAPPED),
    ]
    _lock_file_ex.restype = wintypes.BOOL
    _unlock_file_ex = _kernel32.UnlockFileEx
    _unlock_file_ex.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, ctypes.POINTER(_OVERLAPPED),
    ]
    _unlock_file_ex.restype = wintypes.BOOL
    _LOCKFILE_FAIL_IMMEDIATELY = 0x00000001
    _LOCKFILE_EXCLUSIVE_LOCK = 0x00000002
    _LOCK_CONFLICT_ERRORS = {32, 33, 158}
    _windows_overlapped: dict[int, _OVERLAPPED] = {}
    _windows_overlapped_guard = threading.Lock()

    def _try_lock(descriptor: int, *, exclusive: bool) -> bool:
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(descriptor))
        overlapped = _OVERLAPPED()
        flags = _LOCKFILE_FAIL_IMMEDIATELY
        if exclusive:
            flags |= _LOCKFILE_EXCLUSIVE_LOCK
        if not _lock_file_ex(handle, flags, 0, 0xFFFFFFFF, 0xFFFFFFFF, ctypes.byref(overlapped)):
            code = ctypes.get_last_error()
            if code in _LOCK_CONFLICT_ERRORS:
                return False
            raise ctypes.WinError(code)
        with _windows_overlapped_guard:
            _windows_overlapped[descriptor] = overlapped
        return True

    def _unlock(descriptor: int) -> None:
        with _windows_overlapped_guard:
            overlapped = _windows_overlapped.pop(descriptor, None)
        if overlapped is None:
            return
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(descriptor))
        if not _unlock_file_ex(handle, 0, 0xFFFFFFFF, 0xFFFFFFFF, ctypes.byref(overlapped)):
            raise ctypes.WinError(ctypes.get_last_error())

else:  # pragma: no cover - defensive on unsupported Python targets
    def _try_lock(descriptor: int, *, exclusive: bool) -> bool:
        raise UnsupportedLockingError(f"maintenance locking is unsupported on {os.name!r}")

    def _unlock(descriptor: int) -> None:
        raise UnsupportedLockingError(f"maintenance locking is unsupported on {os.name!r}")


def _acquire(descriptor: int, *, exclusive: bool, timeout: float, path: Path) -> None:
    if _try_lock(descriptor, exclusive=exclusive):
        return
    if timeout == 0:
        mode = "maintenance" if exclusive else "storage participation"
        raise MaintenanceBusyError(f"{mode} lock is busy: {path}")
    deadline = time.monotonic() + timeout
    while not _try_lock(descriptor, exclusive=exclusive):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            mode = "maintenance" if exclusive else "storage participation"
            raise MaintenanceBusyError(f"{mode} lock is busy: {path}")
        time.sleep(min(_RETRY_INTERVAL_SECONDS, remaining))


def _read_bytes_no_follow(path: Path) -> bytes | None:
    expected = _safe_existing_regular(path, label="maintenance metadata path")
    if expected is None:
        return None
    flags = (
        os.O_RDONLY | _O_BINARY
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.EMLINK):
            raise MaintenanceMetadataError(
                f"refusing symbolic-link maintenance metadata path: {path}"
            ) from error
        raise
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise MaintenanceMetadataError(f"maintenance metadata path is not regular: {path}")
        if (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino):
            raise MaintenanceMetadataError("maintenance metadata path changed while it was opened")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(8192, _MAX_METADATA_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > _MAX_METADATA_BYTES:
                raise MaintenanceMetadataError("maintenance metadata is too large")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _read_inspection(database: Path, metadata_path: Path) -> MaintenanceInspection | None:
    raw = _read_bytes_no_follow(metadata_path)
    if raw is None:
        return None
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MaintenanceMetadataError("maintenance metadata is not valid UTF-8 JSON") from error
    if not isinstance(document, dict) or document.get("version") != _FORMAT_VERSION:
        raise MaintenanceMetadataError("unsupported maintenance metadata format")
    if document.get("path") != str(database):
        raise MaintenanceMetadataError("maintenance metadata belongs to another database path")
    fence = document.get("fence")
    if isinstance(fence, bool) or not isinstance(fence, int) or fence < 0:
        raise MaintenanceMetadataError("maintenance metadata has an invalid fence")
    lease_document = document.get("lease")
    if lease_document is None:
        return MaintenanceInspection(path=database, fence=fence, lease=None)
    if not isinstance(lease_document, dict):
        raise MaintenanceMetadataError("maintenance metadata has an invalid lease")
    try:
        raw_expires_at = lease_document["expires_at"]
        if isinstance(raw_expires_at, bool):
            raise TypeError("expires_at cannot be boolean")
        lease = LeaseInfo(
            id=lease_document["id"],
            path=database,
            owner=lease_document["owner"],
            purpose=lease_document["purpose"],
            expires_at=float(raw_expires_at),
            fence=fence,
            pid=lease_document["pid"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise MaintenanceMetadataError("maintenance metadata has invalid lease fields") from error
    if (
        not isinstance(lease.id, str) or not lease.id
        or not isinstance(lease.owner, str) or not lease.owner
        or not isinstance(lease.purpose, str) or not lease.purpose
        or not math.isfinite(lease.expires_at)
        or isinstance(lease.pid, bool) or not isinstance(lease.pid, int) or lease.pid <= 0
    ):
        raise MaintenanceMetadataError("maintenance metadata has invalid lease fields")
    return MaintenanceInspection(path=database, fence=fence, lease=lease)


def _descriptor_document(database: Path, fence: int, lease: LeaseInfo | None) -> dict[str, object]:
    lease_document: dict[str, object] | None = None
    if lease is not None:
        lease_document = {
            "id": lease.id,
            "owner": lease.owner,
            "purpose": lease.purpose,
            "expires_at": lease.expires_at,
            "pid": lease.pid,
        }
    return {
        "version": _FORMAT_VERSION,
        "path": str(database),
        "fence": fence,
        "lease": lease_document,
    }


def _sync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_metadata(path: Path, document: dict[str, object]) -> None:
    _safe_existing_regular(path, label="maintenance metadata path")
    payload = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_BINARY
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("failed to write maintenance metadata")
            view = view[written:]
        os.fsync(descriptor)
        completed_descriptor, descriptor = descriptor, None
        os.close(completed_descriptor)
        _safe_existing_regular(path, label="maintenance metadata path")
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _existing_database(path: Path) -> None:
    try:
        result = path.stat()
    except FileNotFoundError as error:
        raise FileNotFoundError(f"maintenance requires an existing database: {path}") from error
    if not stat.S_ISREG(result.st_mode):
        raise MaintenanceError(f"database path is not a regular file: {path}")


def _assert_not_snapshot_artifact(database: Path) -> None:
    marker = database.parent / _SNAPSHOT_READ_ONLY_MARKER
    try:
        marker.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise SnapshotReadOnlyError(
            f"cannot verify snapshot read-only marker: {marker}"
        ) from error
    raise SnapshotReadOnlyError(
        "authenticated snapshot requires explicit activation; maintenance is disabled"
    )


def _retirement_path(database: Path) -> Path:
    return database.with_name(database.name + _RETIRED_SUFFIX)


def _assert_not_retired(database: Path) -> None:
    marker = _retirement_path(database)
    try:
        result = marker.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise StorageRetiredError(f"cannot verify storage retirement marker: {marker}") from error
    if stat.S_ISLNK(result.st_mode) or not stat.S_ISREG(result.st_mode):
        raise StorageRetiredError(f"storage retirement marker is unsafe: {marker}")
    raise StorageRetiredError(
        "storage was retired by local snapshot activation and cannot be reopened"
    )


def _assert_retirement_allows(database: Path, operation_id: str | None) -> None:
    if operation_id is None:
        _assert_not_retired(database)
        return
    marker = _retirement_path(database)
    try:
        raw = _read_bytes_no_follow(marker)
    except MaintenanceMetadataError as error:
        raise StorageRetiredError(f"storage retirement marker is unsafe: {marker}") from error
    if raw is None:
        return
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StorageRetiredError(f"storage retirement marker is invalid: {marker}") from error
    if not isinstance(document, dict) or document.get("operation_id") != operation_id:
        raise StorageRetiredError(
            "storage was retired by a different local snapshot activation"
        )


@contextmanager
def storage_participant(
    database_path: str | os.PathLike[str],
    *,
    timeout: float = 0,
    lease: Lease | None = None,
) -> Iterator[None]:
    """Hold a shared lock for one complete storage operation lifetime.

    Passing an explicit, valid maintenance ``lease`` is the only bypass for
    work performed by the exclusive holder itself.  A missing database is
    allowed so callers can lock before creating it.
    """
    database, lock_path, _ = _coordination_paths(database_path)
    if lease is not None:
        lease.check(database)
        yield
        return
    _assert_not_retired(database)
    wait = _timeout_seconds(timeout)
    descriptor = _open_lock_file(lock_path)
    acquired = False
    try:
        _acquire(descriptor, exclusive=False, timeout=wait, path=lock_path)
        acquired = True
        _validate_lock_descriptor(descriptor, lock_path)
        _assert_not_retired(database)
        yield
    finally:
        try:
            if acquired:
                _unlock(descriptor)
        finally:
            os.close(descriptor)


def _release_lease(state: _LeaseState) -> None:
    if not state.active:
        return
    state.active = False
    if os.getpid() != state.process_id:
        os.close(state.descriptor)
        return
    failure: BaseException | None = None
    try:
        inspection = _read_inspection(state.path, state.metadata_path)
        if (
            inspection is None
            or inspection.lease is None
            or inspection.fence != state.fence
            or inspection.lease.id != state.lease_id
        ):
            raise InvalidLeaseError("maintenance lease durable identity changed before release")
        _publish_metadata(
            state.metadata_path,
            _descriptor_document(state.path, state.fence, None),
        )
    except BaseException as error:
        failure = error
    try:
        _unlock(state.descriptor)
    except BaseException as error:
        if failure is None:
            failure = error
    finally:
        os.close(state.descriptor)
    if failure is not None:
        raise failure


@contextmanager
def maintenance_lease(
    database_path: str | os.PathLike[str],
    owner_id: str,
    purpose: str,
    lease_seconds: float = 30,
    timeout: float = 0,
    _retired_operation_id: str | None = None,
) -> Iterator[Lease]:
    """Acquire an exclusive, fenced maintenance lease for an existing database."""
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise ValueError("owner_id must be a non-empty string")
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("purpose must be a non-empty string")
    duration = _positive_seconds(lease_seconds, "lease_seconds")
    wait = _timeout_seconds(timeout)
    database, lock_path, metadata_path = _coordination_paths(database_path)
    _assert_not_snapshot_artifact(database)
    _assert_retirement_allows(database, _retired_operation_id)
    _existing_database(database)
    descriptor = _open_lock_file(lock_path)
    try:
        _acquire(descriptor, exclusive=True, timeout=wait, path=lock_path)
        _validate_lock_descriptor(descriptor, lock_path)
        _assert_not_snapshot_artifact(database)
        _assert_retirement_allows(database, _retired_operation_id)
    except BaseException:
        os.close(descriptor)
        raise
    try:
        _existing_database(database)
        previous = _read_inspection(database, metadata_path)
        fence = (0 if previous is None else previous.fence) + 1
        now_wall = time.time()
        now_monotonic = time.monotonic()
        state = _LeaseState(
            path=database,
            lock_path=lock_path,
            metadata_path=metadata_path,
            descriptor=descriptor,
            process_id=os.getpid(),
            lease_id=uuid.uuid4().hex,
            owner=owner_id,
            purpose=purpose,
            fence=fence,
            duration=duration,
            expires_at=now_wall + duration,
            monotonic_deadline=now_monotonic + duration,
        )
        _publish_metadata(
            metadata_path,
            _descriptor_document(
                database,
                fence,
                LeaseInfo(
                    id=state.lease_id,
                    path=database,
                    owner=owner_id,
                    purpose=purpose,
                    expires_at=state.expires_at,
                    fence=fence,
                    pid=state.process_id,
                ),
            ),
        )
    except BaseException:
        # Publishing can fail after the rename (for example, on a directory
        # fsync).  Its active record is safely stale: the OS lock remains the
        # authority and the next exclusive holder will replace it.
        try:
            _unlock(descriptor)
        finally:
            os.close(descriptor)
        raise
    lease = Lease(state)
    try:
        lease.check(database)
        yield lease
    finally:
        _release_lease(state)


def inspect_maintenance(
    database_path: str | os.PathLike[str],
) -> MaintenanceInspection | None:
    """Read durable maintenance state without creating any file or lock."""
    database, _, metadata_path = _coordination_paths(database_path)
    return _read_inspection(database, metadata_path)


__all__ = [
    "InvalidLeaseError",
    "Lease",
    "LeaseInfo",
    "MaintenanceBusyError",
    "MaintenanceError",
    "MaintenanceInspection",
    "MaintenanceMetadataError",
    "SnapshotReadOnlyError",
    "StorageRetiredError",
    "UnsupportedLockingError",
    "inspect_maintenance",
    "maintenance_lease",
    "storage_participant",
]
