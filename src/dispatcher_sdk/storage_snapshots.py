"""Authenticated, closed-set snapshots of caller-declared store groups.

The descriptor is an explicit ownership declaration, not resource discovery.
Snapshotting obtains maintenance exclusion for every registered SQLite member,
but it does not prove business terminal state or quiesce resources which were
not registered.  Snapshot and restored directories carry
``.sdk-snapshot-readonly``; there is intentionally no activation API yet.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
from types import MappingProxyType
from typing import Any, Mapping
import uuid

from .maintenance import Lease, maintenance_lease


_FORMAT = "dispatcher-sdk-store-group-snapshot"
_VERSION = 1
_MANIFEST_NAME = "manifest.json"
_READ_ONLY_MARKER = ".sdk-snapshot-readonly"
_MARKER_CONTENT = b"Dispatcher SDK snapshot; explicit activation is required.\n"
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_MAX_MEMBER_COUNT = 10_000
_MAX_METADATA_ROWS = 256
_MAX_GROUP_BYTES = 1 << 50
_SPACE_OVERHEAD = 1024 * 1024
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class SnapshotError(RuntimeError):
    """Base class for snapshot, verification, and restoration failures."""


class SnapshotValidationError(SnapshotError):
    """A descriptor or snapshot fails closed-set or authenticity validation."""


class SnapshotSpaceError(SnapshotError):
    """The destination filesystem lacks the conservatively estimated space."""


@dataclass(frozen=True, slots=True)
class StoreGroupDescriptor:
    """An explicit closed set of SQLite stores and owned immutable blobs."""

    components: Mapping[str, str | os.PathLike[str]]
    blobs: Mapping[str, str | os.PathLike[str]] = field(default_factory=dict)
    group_id: str = "caller-declared"

    def __post_init__(self) -> None:
        if not isinstance(self.group_id, str) or not _NAME.fullmatch(self.group_id):
            raise SnapshotValidationError("group_id must be a safe non-empty identifier")
        components = _validated_sources(self.components, "component")
        blobs = _validated_sources(self.blobs, "blob")
        if not components:
            raise SnapshotValidationError("a store group must contain at least one SQLite component")
        if len(components) + len(blobs) > _MAX_MEMBER_COUNT - 1:
            raise SnapshotValidationError("store group has too many registered members")
        all_sources = list(components.items()) + list(blobs.items())
        for index, (name, path) in enumerate(all_sources):
            for other_name, other_path in all_sources[index + 1:]:
                if _same_file(path, other_path):
                    raise SnapshotValidationError(
                        f"registered members {name!r} and {other_name!r} alias the same file"
                    )
        object.__setattr__(self, "components", MappingProxyType(components))
        object.__setattr__(self, "blobs", MappingProxyType(blobs))


@dataclass(frozen=True, slots=True)
class VerifiedSnapshot:
    """A fully authenticated and content-verified snapshot."""

    root: Path
    manifest_path: Path
    group_id: str
    components: Mapping[str, Path]
    blobs: Mapping[str, Path]
    manifest: Mapping[str, Any]
    requires_explicit_activation: bool = True


@dataclass(frozen=True, slots=True)
class RestoreResult:
    """A verified restored copy which remains blocked from writer activation."""

    path: Path
    manifest_path: Path
    requires_explicit_activation: bool = True


def _validated_sources(
    supplied: Mapping[str, str | os.PathLike[str]], label: str
) -> dict[str, Path]:
    if not isinstance(supplied, Mapping):
        raise SnapshotValidationError(f"{label}s must be a mapping")
    result: dict[str, Path] = {}
    for name, raw_path in supplied.items():
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise SnapshotValidationError(f"unsafe {label} name: {name!r}")
        if name in result:
            raise SnapshotValidationError(f"duplicate {label} name: {name!r}")
        path = _existing_regular_without_symlinks(raw_path, f"{label} {name!r}")
        result[name] = path
    return result


def _lexical_absolute(raw_path: str | os.PathLike[str], label: str) -> Path:
    value = os.fspath(raw_path)
    if not value:
        raise SnapshotValidationError(f"{label} path is empty")
    lexical = Path(value).expanduser()
    if ".." in lexical.parts:
        raise SnapshotValidationError(f"{label} path contains parent traversal")
    return Path(os.path.abspath(lexical))


def _reject_symlink_components(path: Path, label: str, *, include_leaf: bool = True) -> None:
    parts = path.parts
    current = Path(parts[0])
    limit = len(parts) if include_leaf else len(parts) - 1
    for part in parts[1:limit]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            raise SnapshotValidationError(f"{label} path parent does not exist: {current}")
        if stat.S_ISLNK(mode):
            raise SnapshotValidationError(f"{label} path traverses a symbolic link: {current}")


def _existing_regular_without_symlinks(
    raw_path: str | os.PathLike[str], label: str
) -> Path:
    path = _lexical_absolute(raw_path, label)
    _reject_symlink_components(path, label)
    try:
        result = path.lstat()
    except FileNotFoundError as error:
        raise SnapshotValidationError(f"{label} does not exist: {path}") from error
    if stat.S_ISLNK(result.st_mode) or not stat.S_ISREG(result.st_mode):
        raise SnapshotValidationError(f"{label} must be a non-symlink regular file: {path}")
    return path


def _same_file(left: Path, right: Path) -> bool:
    left_stat = left.stat()
    right_stat = right.stat()
    return (left_stat.st_dev, left_stat.st_ino) == (right_stat.st_dev, right_stat.st_ino)


def _file_identity(path: Path) -> tuple[int, int, int, int]:
    result = path.lstat()
    if stat.S_ISLNK(result.st_mode) or not stat.S_ISREG(result.st_mode):
        raise SnapshotValidationError(f"registered source is no longer a regular file: {path}")
    return result.st_dev, result.st_ino, result.st_size, result.st_mtime_ns


def _sqlite_source_identity(path: Path) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int] | None]:
    wal = Path(str(path) + "-wal")
    try:
        wal_result = wal.lstat()
    except FileNotFoundError:
        wal_identity = None
    else:
        if stat.S_ISLNK(wal_result.st_mode) or not stat.S_ISREG(wal_result.st_mode):
            raise SnapshotValidationError(f"SQLite WAL sidecar is unsafe: {wal}")
        wal_identity = (
            wal_result.st_dev, wal_result.st_ino, wal_result.st_size, wal_result.st_mtime_ns
        )
    return _file_identity(path), wal_identity


def _revalidate_group(group: StoreGroupDescriptor) -> None:
    sources = list(group.components.items()) + list(group.blobs.items())
    for name, path in sources:
        _existing_regular_without_symlinks(path, f"registered member {name!r}")
    for index, (name, path) in enumerate(sources):
        for other_name, other_path in sources[index + 1:]:
            if _same_file(path, other_path):
                raise SnapshotValidationError(
                    f"registered members {name!r} and {other_name!r} now alias the same file"
                )


def _signing_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise SnapshotValidationError("signing_key must contain at least 32 bytes")
    return key


def _canonical(document: Mapping[str, Any]) -> bytes:
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _unsigned_manifest(document: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = dict(document)
    authentication = unsigned.get("authentication")
    if not isinstance(authentication, dict):
        raise SnapshotValidationError("manifest authentication section is invalid")
    unsigned["authentication"] = {
        key: value for key, value in authentication.items() if key != "tag"
    }
    return unsigned


def _authenticate(document: dict[str, Any], key: bytes) -> None:
    tag = hmac.new(key, _canonical(_unsigned_manifest(document)), hashlib.sha256).hexdigest()
    document["authentication"]["tag"] = tag


def _verify_authentication(document: Mapping[str, Any], key: bytes) -> None:
    authentication = document.get("authentication")
    if not isinstance(authentication, dict):
        raise SnapshotValidationError("manifest authentication section is invalid")
    if authentication.get("algorithm") != "HMAC-SHA256":
        raise SnapshotValidationError("unsupported manifest authentication algorithm")
    expected_key_id = hashlib.sha256(key).hexdigest()[:32]
    if authentication.get("key_id") != expected_key_id:
        raise SnapshotValidationError("snapshot authentication key does not match")
    tag = authentication.get("tag")
    if not isinstance(tag, str) or len(tag) != 64:
        raise SnapshotValidationError("manifest authentication tag is invalid")
    calculated = hmac.new(key, _canonical(_unsigned_manifest(document)), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(tag, calculated):
        raise SnapshotValidationError("snapshot authentication failed")


def _safe_destination(raw_path: str | os.PathLike[str], label: str) -> Path:
    destination = _lexical_absolute(raw_path, label)
    _reject_symlink_components(destination, label, include_leaf=False)
    try:
        destination.lstat()
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(destination)
    parent = destination.parent
    result = parent.lstat()
    if stat.S_ISLNK(result.st_mode) or not stat.S_ISDIR(result.st_mode):
        raise SnapshotValidationError(f"{label} parent must be a non-symlink directory")
    return destination


def _open_read_no_follow(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise SnapshotValidationError(f"cannot safely open snapshot member: {path}") from error
    opened = os.fstat(descriptor)
    if not stat.S_ISREG(opened.st_mode):
        os.close(descriptor)
        raise SnapshotValidationError(f"snapshot member is not a regular file: {path}")
    current = path.lstat()
    if stat.S_ISLNK(current.st_mode) or (
        opened.st_dev, opened.st_ino
    ) != (current.st_dev, current.st_ino):
        os.close(descriptor)
        raise SnapshotValidationError(f"snapshot member changed while opening: {path}")
    return descriptor


def _copy_and_hash(source: Path, destination: Path) -> tuple[int, str]:
    source_descriptor = _open_read_no_follow(source)
    before = os.fstat(source_descriptor)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        destination_descriptor = os.open(destination, flags, 0o600)
    except BaseException:
        os.close(source_descriptor)
        raise
    digest = hashlib.sha256()
    size = 0
    try:
        while True:
            chunk = os.read(source_descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_descriptor, view)
                if written <= 0:
                    raise OSError("failed to copy snapshot member")
                view = view[written:]
        os.fsync(destination_descriptor)
        after = os.fstat(source_descriptor)
        if (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
        ) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise SnapshotValidationError(f"source changed while copying: {source}")
    finally:
        os.close(destination_descriptor)
        os.close(source_descriptor)
    return size, digest.hexdigest()


def _hash_file(path: Path) -> tuple[int, str]:
    descriptor = _open_read_no_follow(path)
    digest = hashlib.sha256()
    size = 0
    try:
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    finally:
        os.close(descriptor)
    return size, digest.hexdigest()


def _sqlite_uri(path: Path) -> str:
    return path.as_uri() + "?mode=ro"


def _backup_sqlite(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(_sqlite_uri(source), uri=True, timeout=30)
    try:
        source_connection.execute("PRAGMA query_only=ON")
        source_connection.execute("PRAGMA trusted_schema=OFF")
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
            destination_connection.commit()
            # The snapshot is a self-contained database file.  A source in
            # WAL mode must not cause verification reads to materialize
            # unregistered -wal/-shm files inside the closed artifact set.
            destination_connection.execute("PRAGMA journal_mode=DELETE")
            check = [row[0] for row in destination_connection.execute("PRAGMA quick_check")]
            if check != ["ok"]:
                raise SnapshotValidationError(
                    f"SQLite backup failed quick_check for {source}: {'; '.join(check)}"
                )
        finally:
            destination_connection.close()
    except sqlite3.Error as error:
        raise SnapshotValidationError(f"cannot snapshot SQLite component {source}: {error}") from error
    finally:
        source_connection.close()
    descriptor = os.open(destination, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sqlite_details(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(_sqlite_uri(path), uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        pragmas = {
            name: int(connection.execute(f"PRAGMA {name}").fetchone()[0])
            for name in (
                "application_id", "user_version", "schema_version", "page_size",
                "page_count", "freelist_count",
            )
        }
        schema_rows = connection.execute(
            "SELECT type,name,tbl_name,COALESCE(sql,'') FROM sqlite_schema ORDER BY type,name"
        ).fetchall()
        schema_digest = hashlib.sha256(_canonical({"schema": schema_rows})).hexdigest()
        markers: dict[str, dict[str, Any]] = {}
        highwater: dict[str, dict[str, Any]] = {}
        table_names = [row[1] for row in schema_rows if row[0] == "table"]
        for table_name in table_names:
            columns = [row[1] for row in connection.execute(
                f"PRAGMA table_info({_quote_identifier(table_name)})"
            )]
            if table_name.endswith("_meta"):
                count = int(connection.execute(
                    f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}"
                ).fetchone()[0])
                if count > _MAX_METADATA_ROWS:
                    raise SnapshotValidationError(
                        f"SQLite metadata table is unexpectedly large: {table_name}"
                    )
                marker_rows: list[list[Any]] = []
                for row in connection.execute(
                    f"SELECT * FROM {_quote_identifier(table_name)}"
                ):
                    marker_rows.append([_json_scalar(value) for value in row])
                encoded_rows = sorted(_canonical({"row": row}) for row in marker_rows)
                marker_digest = hashlib.sha256()
                for encoded_row in encoded_rows:
                    marker_digest.update(hashlib.sha256(encoded_row).digest())
                markers[table_name] = {
                    "columns": columns,
                    "rows": [json.loads(encoded.decode("utf-8"))["row"] for encoded in encoded_rows],
                    "sha256": marker_digest.hexdigest(),
                }
            sequence_columns = [
                name for name in columns
                if name.lower() in {"seq", "sequence", "revision", "highwater", "high_water"}
                or name.lower().endswith("_sequence")
            ]
            if sequence_columns:
                highwater[table_name] = {}
                for column in sequence_columns:
                    value = connection.execute(
                        f"SELECT MAX({_quote_identifier(column)}) FROM {_quote_identifier(table_name)}"
                    ).fetchone()[0]
                    highwater[table_name][column] = _json_scalar(value)
        return {
            "pragmas": pragmas,
            "schema_sha256": schema_digest,
            "schema_markers": markers,
            "sequence_highwater": highwater,
        }
    finally:
        connection.close()


def _json_scalar(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return {"float": repr(value)}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest(), "length": len(value)}
    return {"text": str(value)}


def _estimated_output_bytes(group: StoreGroupDescriptor) -> int:
    total = len(_MARKER_CONTENT) + _SPACE_OVERHEAD
    for path in group.components.values():
        connection = sqlite3.connect(_sqlite_uri(path), uri=True)
        try:
            connection.execute("PRAGMA query_only=ON")
            page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        except sqlite3.Error as error:
            raise SnapshotValidationError(f"cannot inspect SQLite component {path}: {error}") from error
        finally:
            connection.close()
        total += max(path.stat().st_size, page_size * page_count)
    total += sum(path.stat().st_size for path in group.blobs.values())
    if total > _MAX_GROUP_BYTES:
        raise SnapshotSpaceError("store group exceeds the supported snapshot size bound")
    return total


def _sync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_manifest(root: Path, manifest: dict[str, Any]) -> Path:
    payload = _canonical(manifest) + b"\n"
    temporary = root / f".{_MANIFEST_NAME}.{uuid.uuid4().hex}.pending"
    descriptor: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("failed to write snapshot manifest")
            view = view[written:]
        os.fsync(descriptor)
        completed_descriptor, descriptor = descriptor, None
        os.close(completed_descriptor)
        manifest_path = root / _MANIFEST_NAME
        os.link(temporary, manifest_path, follow_symlinks=False)
        _sync_directory(root)
        return manifest_path
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _created_directory(path: Path) -> tuple[int, int]:
    os.mkdir(path, 0o700)
    result = path.lstat()
    return result.st_dev, result.st_ino


def _cleanup_owned_directory(path: Path, identity: tuple[int, int]) -> None:
    try:
        current = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISDIR(current.st_mode) and (current.st_dev, current.st_ino) == identity:
        shutil.rmtree(path)


def _failpoint(name: str) -> None:
    """Internal exception/crash boundary patched by fault-injection tests."""


def _check_leases(leases: Mapping[Path, Lease]) -> None:
    for path, lease in leases.items():
        lease.check(path)


def snapshot_store_group(
    group: StoreGroupDescriptor,
    destination: str | os.PathLike[str],
    *,
    signing_key: bytes,
    owner_id: str,
    lease_seconds: float = 30,
) -> Path:
    """Create and authenticate one snapshot; return its committed manifest path.

    The destination must not exist.  Registered SDK connections block the
    maintenance leases.  Successful acquisition proves storage exclusion only;
    it does not prove that Runs are terminal or external Effects are quiescent.
    """
    if not isinstance(group, StoreGroupDescriptor):
        raise TypeError("group must be a StoreGroupDescriptor")
    key = _signing_key(signing_key)
    target = _safe_destination(destination, "snapshot destination")
    _revalidate_group(group)
    with ExitStack() as stack:
        leases: dict[Path, Lease] = {}
        for source in sorted(group.components.values(), key=os.fspath):
            leases[source] = stack.enter_context(
                maintenance_lease(
                    source, owner_id, "snapshot-store-group", lease_seconds=lease_seconds
                )
            )
        _revalidate_group(group)
        _check_leases(leases)
        estimated = _estimated_output_bytes(group)
        free = shutil.disk_usage(target.parent).free
        if free < estimated:
            raise SnapshotSpaceError(
                f"snapshot needs at least {estimated} bytes but only {free} are available"
            )
        identity = _created_directory(target)
        try:
            _failpoint("snapshot.after_destination_created")
            members: list[dict[str, Any]] = []
            component_manifest: dict[str, str] = {}
            blob_manifest: dict[str, str] = {}
            source_identities = {
                source: _sqlite_source_identity(source)
                for source in group.components.values()
            }
            for name, source in sorted(group.components.items()):
                _check_leases(leases)
                source_identity = source_identities[source]
                relative = f"component-{name}.sqlite3"
                output = target / PurePosixPath(relative)
                _backup_sqlite(source, output)
                if _sqlite_source_identity(source) != source_identity:
                    raise SnapshotValidationError(f"SQLite source changed during backup: {source}")
                size, digest = _hash_file(output)
                details = _sqlite_details(output)
                members.append({
                    "kind": "sqlite",
                    "name": name,
                    "path": relative,
                    "size": size,
                    "sha256": digest,
                    "sqlite": details,
                })
                component_manifest[name] = relative
                _failpoint(f"snapshot.after_component.{name}")
            for name, source in sorted(group.blobs.items()):
                _check_leases(leases)
                relative = f"blob-{name}.blob"
                output = target / PurePosixPath(relative)
                size, digest = _copy_and_hash(source, output)
                members.append({
                    "kind": "blob", "name": name, "path": relative,
                    "size": size, "sha256": digest,
                })
                blob_manifest[name] = relative
                _failpoint(f"snapshot.after_blob.{name}")
            marker = target / _READ_ONLY_MARKER
            marker_descriptor = os.open(
                marker,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            try:
                marker_view = memoryview(_MARKER_CONTENT)
                while marker_view:
                    written = os.write(marker_descriptor, marker_view)
                    if written <= 0:
                        raise OSError("failed to write snapshot activation marker")
                    marker_view = marker_view[written:]
                os.fsync(marker_descriptor)
            finally:
                os.close(marker_descriptor)
            marker_size, marker_digest = _hash_file(marker)
            members.append({
                "kind": "activation-marker", "name": _READ_ONLY_MARKER,
                "path": _READ_ONLY_MARKER, "size": marker_size, "sha256": marker_digest,
            })
            _check_leases(leases)
            for source, identity_before in source_identities.items():
                if _sqlite_source_identity(source) != identity_before:
                    raise SnapshotValidationError(
                        f"SQLite source changed while snapshotting the store group: {source}"
                    )
            manifest: dict[str, Any] = {
                "format": _FORMAT,
                "version": _VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "group": {
                    "id": group.group_id,
                    "components": component_manifest,
                    "blobs": blob_manifest,
                    "declaration": "caller-declared-closed-set",
                },
                "members": sorted(members, key=lambda item: item["path"]),
                "activation": {
                    "requires_explicit_activation": True,
                    "marker": _READ_ONLY_MARKER,
                    "activation_api_available": False,
                },
                "consistency": {
                    "storage_maintenance_exclusion": True,
                    "business_terminal_state_proven": False,
                    "undeclared_resources_discovered": False,
                },
                "authentication": {
                    "algorithm": "HMAC-SHA256",
                    "key_id": hashlib.sha256(key).hexdigest()[:32],
                },
            }
            _authenticate(manifest, key)
            _failpoint("snapshot.before_manifest_publish")
            _check_leases(leases)
            manifest_path = _publish_manifest(target, manifest)
            _failpoint("snapshot.after_manifest_publish")
            verify_snapshot(manifest_path, key)
            _check_leases(leases)
            return manifest_path
        except BaseException:
            _cleanup_owned_directory(target, identity)
            raise


def _snapshot_root(path: str | os.PathLike[str]) -> tuple[Path, Path]:
    supplied = _lexical_absolute(path, "snapshot")
    _reject_symlink_components(supplied, "snapshot")
    if supplied.name == _MANIFEST_NAME:
        root, manifest = supplied.parent, supplied
    else:
        root, manifest = supplied, supplied / _MANIFEST_NAME
    root_result = root.lstat()
    if stat.S_ISLNK(root_result.st_mode) or not stat.S_ISDIR(root_result.st_mode):
        raise SnapshotValidationError("snapshot root must be a non-symlink directory")
    return root, manifest


def _read_manifest(path: Path) -> tuple[bytes, dict[str, Any]]:
    descriptor = _open_read_no_follow(path)
    chunks: list[bytes] = []
    size = 0
    try:
        while True:
            chunk = os.read(descriptor, min(65536, _MAX_MANIFEST_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > _MAX_MANIFEST_BYTES:
                raise SnapshotValidationError("snapshot manifest is too large")
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SnapshotValidationError("snapshot manifest is not valid UTF-8 JSON") from error
    if not isinstance(document, dict):
        raise SnapshotValidationError("snapshot manifest root must be an object")
    return raw, document


def _validated_member_path(relative: Any) -> PurePosixPath:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise SnapshotValidationError("snapshot member has an unsafe path")
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise SnapshotValidationError("snapshot member has an unsafe path")
    if path.as_posix() in (_MANIFEST_NAME,):
        raise SnapshotValidationError("manifest cannot list itself as a payload member")
    return path


def _actual_snapshot_files(root: Path) -> tuple[set[str], set[str]]:
    actual: set[str] = set()
    directories: set[str] = set()
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        for directory_name in directory_names:
            candidate = current / directory_name
            if stat.S_ISLNK(candidate.lstat().st_mode):
                raise SnapshotValidationError(f"snapshot contains a symbolic link: {candidate}")
            directories.add(candidate.relative_to(root).as_posix())
        for file_name in file_names:
            candidate = current / file_name
            result = candidate.lstat()
            if stat.S_ISLNK(result.st_mode) or not stat.S_ISREG(result.st_mode):
                raise SnapshotValidationError(f"snapshot contains an unsafe member: {candidate}")
            actual.add(candidate.relative_to(root).as_posix())
    return actual, directories


def verify_snapshot(
    path: str | os.PathLike[str], signing_key: bytes
) -> VerifiedSnapshot:
    """Authenticate a manifest first, then validate its exact member set and bytes."""
    key = _signing_key(signing_key)
    root, manifest_path = _snapshot_root(path)
    _, manifest = _read_manifest(manifest_path)
    # Do not resolve, open, or otherwise trust any manifest member path before
    # this authentication succeeds.
    _verify_authentication(manifest, key)
    if manifest.get("format") != _FORMAT or manifest.get("version") != _VERSION:
        raise SnapshotValidationError("unsupported snapshot manifest format")
    members = manifest.get("members")
    if not isinstance(members, list) or not members or len(members) > _MAX_MEMBER_COUNT:
        raise SnapshotValidationError("snapshot manifest has an invalid member list")
    declared_paths: set[str] = set()
    member_inodes: set[tuple[int, int]] = set()
    component_paths: dict[str, Path] = {}
    blob_paths: dict[str, Path] = {}
    for member in members:
        if not isinstance(member, dict):
            raise SnapshotValidationError("snapshot manifest has an invalid member")
        relative = _validated_member_path(member.get("path"))
        relative_text = relative.as_posix()
        if relative_text in declared_paths:
            raise SnapshotValidationError("snapshot manifest repeats a member path")
        declared_paths.add(relative_text)
        name = member.get("name")
        kind = member.get("kind")
        if not isinstance(name, str) or (kind != "activation-marker" and not _NAME.fullmatch(name)):
            raise SnapshotValidationError("snapshot member name is invalid")
        size = member.get("size")
        digest = member.get("sha256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise SnapshotValidationError("snapshot member size is invalid")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SnapshotValidationError("snapshot member digest is invalid")
        member_path = root.joinpath(*relative.parts)
        actual_size, actual_digest = _hash_file(member_path)
        member_stat = member_path.stat()
        member_identity = (member_stat.st_dev, member_stat.st_ino)
        if member_identity in member_inodes:
            raise SnapshotValidationError("snapshot payload members must not be hard-link aliases")
        member_inodes.add(member_identity)
        if actual_size != size or not hmac.compare_digest(actual_digest, digest):
            raise SnapshotValidationError(f"snapshot member digest mismatch: {relative_text}")
        if kind == "sqlite":
            if name in component_paths or relative_text != f"component-{name}.sqlite3":
                raise SnapshotValidationError("snapshot SQLite member mapping is invalid")
            try:
                connection = sqlite3.connect(_sqlite_uri(member_path), uri=True)
                check = [row[0] for row in connection.execute("PRAGMA quick_check")]
            except sqlite3.Error as error:
                raise SnapshotValidationError(f"snapshot SQLite member is invalid: {name}") from error
            finally:
                if "connection" in locals():
                    connection.close()
                    del connection
            if check != ["ok"]:
                raise SnapshotValidationError(f"snapshot SQLite member failed quick_check: {name}")
            if member.get("sqlite") != _sqlite_details(member_path):
                raise SnapshotValidationError(f"snapshot SQLite metadata mismatch: {name}")
            component_paths[name] = member_path
        elif kind == "blob":
            if name in blob_paths or relative_text != f"blob-{name}.blob":
                raise SnapshotValidationError("snapshot blob member mapping is invalid")
            blob_paths[name] = member_path
        elif kind == "activation-marker":
            if name != _READ_ONLY_MARKER or relative_text != _READ_ONLY_MARKER:
                raise SnapshotValidationError("snapshot activation marker is invalid")
        else:
            raise SnapshotValidationError("snapshot member kind is invalid")
    actual, directories = _actual_snapshot_files(root)
    expected = declared_paths | {_MANIFEST_NAME}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SnapshotValidationError(f"snapshot closed set differs; missing={missing}, extra={extra}")
    if directories:
        raise SnapshotValidationError(
            f"snapshot directory set differs from the format: {sorted(directories)}"
        )
    group = manifest.get("group")
    activation = manifest.get("activation")
    if (
        not isinstance(group, dict)
        or not isinstance(group.get("id"), str)
        or not _NAME.fullmatch(group["id"])
    ):
        raise SnapshotValidationError("snapshot group descriptor is invalid")
    if group.get("declaration") != "caller-declared-closed-set":
        raise SnapshotValidationError("snapshot does not declare a closed member set")
    expected_components = group.get("components")
    expected_blobs = group.get("blobs")
    if expected_components != {name: path.relative_to(root).as_posix() for name, path in component_paths.items()}:
        raise SnapshotValidationError("snapshot component mapping differs from its member set")
    if expected_blobs != {name: path.relative_to(root).as_posix() for name, path in blob_paths.items()}:
        raise SnapshotValidationError("snapshot blob mapping differs from its member set")
    if (
        not isinstance(activation, dict)
        or activation.get("requires_explicit_activation") is not True
        or activation.get("activation_api_available") is not False
        or activation.get("marker") != _READ_ONLY_MARKER
        or _READ_ONLY_MARKER not in declared_paths
    ):
        raise SnapshotValidationError("snapshot activation gate is invalid")
    marker_member = next(
        (member for member in members if member.get("kind") == "activation-marker"), None
    )
    if (
        marker_member is None
        or marker_member["size"] != len(_MARKER_CONTENT)
        or marker_member["sha256"] != hashlib.sha256(_MARKER_CONTENT).hexdigest()
    ):
        raise SnapshotValidationError("snapshot activation marker content is invalid")
    return VerifiedSnapshot(
        root=root,
        manifest_path=manifest_path,
        group_id=group["id"],
        components=MappingProxyType(component_paths),
        blobs=MappingProxyType(blob_paths),
        manifest=MappingProxyType(manifest),
    )


def restore_snapshot(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    signing_key: bytes,
) -> RestoreResult:
    """Copy a verified snapshot to a fresh directory and publish its manifest last."""
    verified = verify_snapshot(source, signing_key)
    target = _safe_destination(destination, "restore destination")
    if target.is_relative_to(verified.root):
        raise SnapshotValidationError("restore destination cannot be inside its source snapshot")
    required = sum(
        int(member["size"]) for member in verified.manifest["members"]
    ) + _SPACE_OVERHEAD
    if required > _MAX_GROUP_BYTES:
        raise SnapshotSpaceError("snapshot exceeds the supported restore size bound")
    free = shutil.disk_usage(target.parent).free
    if free < required:
        raise SnapshotSpaceError(
            f"restore needs at least {required} bytes but only {free} are available"
        )
    identity = _created_directory(target)
    try:
        _failpoint("restore.after_destination_created")
        for member in verified.manifest["members"]:
            relative = _validated_member_path(member["path"])
            source_path = verified.root.joinpath(*relative.parts)
            destination_path = target.joinpath(*relative.parts)
            size, digest = _copy_and_hash(source_path, destination_path)
            if size != member["size"] or not hmac.compare_digest(digest, member["sha256"]):
                raise SnapshotValidationError(
                    f"snapshot source changed during restore: {relative.as_posix()}"
                )
            _failpoint(f"restore.after_member.{relative.as_posix()}")
        _, current_manifest = _read_manifest(verified.manifest_path)
        _verify_authentication(current_manifest, _signing_key(signing_key))
        if current_manifest != dict(verified.manifest):
            raise SnapshotValidationError("snapshot manifest changed during restore")
        _failpoint("restore.before_manifest_publish")
        manifest_path = _publish_manifest(target, current_manifest)
        _failpoint("restore.after_manifest_publish")
        verify_snapshot(manifest_path, signing_key)
        return RestoreResult(path=target, manifest_path=manifest_path)
    except BaseException:
        _cleanup_owned_directory(target, identity)
        raise


__all__ = [
    "RestoreResult",
    "SnapshotError",
    "SnapshotSpaceError",
    "SnapshotValidationError",
    "StoreGroupDescriptor",
    "VerifiedSnapshot",
    "restore_snapshot",
    "snapshot_store_group",
    "verify_snapshot",
]
