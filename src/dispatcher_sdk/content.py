"""Content-addressed storage for strict JSON values.

The codec deliberately has no schema-management or transaction-management
side effects.  Callers install ``CONTENT_SCHEMA`` and commit or roll back the
transaction containing :func:`encode_value`.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from typing import Any


class ContentReadBudget:
    """A cumulative encoded-byte allowance shared across decoded values.

    Each root and each fetched object body consumes bytes. Cached objects within
    one decode are counted once; a subsequent decode fetch is counted again.
    This complements the per-value logical/depth limits and changes no encoding.
    """

    def __init__(self, max_encoded_bytes: int):
        self.remaining = _positive_integer(max_encoded_bytes, "max_encoded_bytes")

    def consume(self, byte_count: int) -> None:
        if type(byte_count) is not int or byte_count < 0:
            raise ValueError("byte_count must be a nonnegative integer")
        if byte_count > self.remaining:
            raise ContentSizeLimitError("content exceeds maximum cumulative encoded read budget")
        self.remaining -= byte_count

CONTENT_SCHEMA = """
CREATE TABLE sdk_content_objects(
    digest TEXT PRIMARY KEY,
    encoded TEXT NOT NULL,
    logical_bytes INTEGER NOT NULL
);
"""

CONTENT_PREFIX = "sdk-content-v1:"
DEFAULT_THRESHOLD = 64 * 1024
MAX_LOGICAL_BYTES = 128 * 1024 * 1024
MAX_ENCODED_BYTES = 256 * 1024 * 1024
MAX_DEPTH = 100

_DIGEST_DOMAIN = b"dispatcher-sdk-content-object-v1\x00"
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")


class ContentIntegrityError(ValueError):
    """Stored content is missing, malformed, or fails an integrity check."""


class ContentSizeLimitError(ContentIntegrityError):
    """A logical, encoded or cumulative byte allowance was exceeded."""


def _positive_integer(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _canonical(value: Any) -> str:
    """Match orchestrator.contracts.canonical without importing that package."""

    def validate(item: Any) -> None:
        if item is None or type(item) in {bool, str, int, float}:
            return
        if type(item) is list:
            for child in item:
                validate(child)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                validate(child)
            return
        raise ValueError("value must be strict JSON with string object keys")

    try:
        validate(value)
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (RecursionError, ValueError, TypeError) as exc:
        raise ValueError("value must be finite, acyclic strict JSON") from exc


def _canonical_bytes(value: Any) -> int:
    return len(_canonical(value).encode("utf-8"))


def _object_digest(encoded: str) -> str:
    return hashlib.sha256(_DIGEST_DOMAIN + encoded.encode("utf-8")).hexdigest()


def _encoded_limit(maximum: int, requested: int) -> int:
    # Tiny logical budgets should also impose a small physical budget, while
    # retaining enough headroom for typed/ref nodes at threshold=1.
    derived = max(4096, maximum * 128 + 1024)
    return min(requested, derived)


def _utf8_size_with_limit(value: str, limit: int) -> int:
    """Measure UTF-8 without allocating one encoded copy of the whole string."""
    if len(value) > limit:
        return limit + 1
    total = 0
    for offset in range(0, len(value), 64 * 1024):
        total += len(value[offset : offset + 64 * 1024].encode("utf-8"))
        if total > limit:
            return total
    return total


class _Encoder:
    def __init__(self, threshold: int, maximum: int, encoded_limit: int, max_depth: int):
        self.threshold = threshold
        self.maximum = maximum
        self.encoded_limit = encoded_limit
        self.max_depth = max_depth
        self.active: set[int] = set()
        self.objects: dict[str, tuple[str, int]] = {}

    def build(self, value: Any, depth: int = 0) -> tuple[list[Any], int]:
        if depth > self.max_depth:
            raise ValueError(f"JSON value exceeds maximum depth {self.max_depth}")

        if value is None:
            node: list[Any] = ["null"]
            logical_bytes = 4
        elif type(value) is bool:
            node = ["bool", value]
            logical_bytes = 4 if value else 5
        elif type(value) is int:
            node = ["int", value]
            logical_bytes = _canonical_bytes(value)
        elif type(value) is float:
            if not math.isfinite(value):
                raise ValueError("value must be finite, acyclic strict JSON")
            node = ["float", value]
            logical_bytes = _canonical_bytes(value)
        elif type(value) is str:
            node = ["string", value]
            logical_bytes = _canonical_bytes(value)
        elif type(value) is list:
            node, logical_bytes = self._list(value, depth)
        elif type(value) is dict and all(type(key) is str for key in value):
            node, logical_bytes = self._dict(value, depth)
        else:
            raise ValueError("value must be strict JSON with string object keys")

        if logical_bytes > self.maximum:
            raise ValueError(
                f"JSON value is {logical_bytes} bytes; maximum is {self.maximum}"
            )
        # Keep the deepest logical node inline so a depth-N value never
        # creates N+1 references that its decoder would reject.
        if logical_bytes >= self.threshold and depth < self.max_depth:
            encoded = _canonical(node)
            if _utf8_size_with_limit(encoded, self.encoded_limit) > self.encoded_limit:
                raise ValueError(
                    f"encoded content exceeds maximum size {self.encoded_limit} bytes"
                )
            digest = _object_digest(encoded)
            existing = self.objects.get(digest)
            record = (encoded, logical_bytes)
            if existing is not None and existing != record:
                raise ContentIntegrityError("content digest collision")
            self.objects[digest] = record
            return ["ref", digest, logical_bytes], logical_bytes
        return node, logical_bytes

    def _list(self, value: list[Any], depth: int) -> tuple[list[Any], int]:
        identity = id(value)
        if identity in self.active:
            raise ValueError("value must be finite, acyclic strict JSON")
        self.active.add(identity)
        try:
            children: list[list[Any]] = []
            logical_bytes = 2
            for index, item in enumerate(value):
                child, child_bytes = self.build(item, depth + 1)
                children.append(child)
                logical_bytes += child_bytes + (1 if index else 0)
                if logical_bytes > self.maximum:
                    raise ValueError(
                        f"JSON value exceeds maximum size {self.maximum} bytes"
                    )
            return ["list", children], logical_bytes
        finally:
            self.active.remove(identity)

    def _dict(self, value: dict[str, Any], depth: int) -> tuple[list[Any], int]:
        identity = id(value)
        if identity in self.active:
            raise ValueError("value must be finite, acyclic strict JSON")
        self.active.add(identity)
        try:
            entries: list[list[Any]] = []
            logical_bytes = 2
            for index, key in enumerate(sorted(value)):
                child, child_bytes = self.build(value[key], depth + 1)
                entries.append([key, child])
                logical_bytes += _canonical_bytes(key) + 1 + child_bytes
                logical_bytes += 1 if index else 0
                if logical_bytes > self.maximum:
                    raise ValueError(
                        f"JSON value exceeds maximum size {self.maximum} bytes"
                    )
            return ["dict", entries], logical_bytes
        finally:
            self.active.remove(identity)


def _insert_objects(
    connection: sqlite3.Connection, objects: dict[str, tuple[str, int]]
) -> None:
    for digest, (encoded, logical_bytes) in objects.items():
        connection.execute(
            "INSERT OR IGNORE INTO sdk_content_objects(digest, encoded, logical_bytes) "
            "VALUES(?,?,?)",
            (digest, encoded, logical_bytes),
        )
        row = connection.execute(
            "SELECT encoded, logical_bytes FROM sdk_content_objects WHERE digest=?",
            (digest,),
        ).fetchone()
        if row is None or row[0] != encoded or row[1] != logical_bytes:
            raise ContentIntegrityError(
                f"existing content object {digest} does not match its digest"
            )


def encode_value(
    connection: sqlite3.Connection,
    value: Any,
    threshold: int = DEFAULT_THRESHOLD,
    *,
    max_logical_bytes: int = MAX_LOGICAL_BYTES,
    max_encoded_bytes: int = MAX_ENCODED_BYTES,
    max_depth: int = MAX_DEPTH,
) -> str:
    """Encode a strict JSON value and insert large nodes into ``connection``.

    The function neither creates the object table nor commits the transaction.
    Object rows use ``INSERT OR IGNORE`` and are verified after insertion.
    """

    threshold = _positive_integer(threshold, "threshold")
    maximum = _positive_integer(max_logical_bytes, "max_logical_bytes")
    requested_encoded = _positive_integer(max_encoded_bytes, "max_encoded_bytes")
    encoded_limit = _encoded_limit(maximum, requested_encoded)
    depth_limit = _positive_integer(max_depth, "max_depth")
    encoder = _Encoder(threshold, maximum, encoded_limit, depth_limit)
    root, _ = encoder.build(value)
    root_encoded = _canonical(root)
    root_bytes = _utf8_size_with_limit(root_encoded, encoded_limit)
    if len(CONTENT_PREFIX.encode("utf-8")) + root_bytes > encoded_limit:
        raise ValueError(f"encoded content exceeds maximum size {encoded_limit} bytes")
    encoded = CONTENT_PREFIX + root_encoded
    _insert_objects(connection, encoder.objects)
    return encoded


class _Decoder:
    def __init__(
        self,
        connection: sqlite3.Connection,
        maximum: int,
        max_depth: int,
        encoded_limit: int | None = None,
        read_budget: ContentReadBudget | None = None,
    ):
        self.connection = connection
        self.read_budget = read_budget
        self.maximum = maximum
        self.encoded_limit = (
            _encoded_limit(maximum, MAX_ENCODED_BYTES)
            if encoded_limit is None
            else encoded_limit
        )
        self.max_depth = max_depth
        self.active: set[str] = set()
        self.verified: dict[str, tuple[list[Any], int]] = {}

    def parse(self, encoded: str, label: str) -> list[Any]:
        if _utf8_size_with_limit(encoded, self.encoded_limit) > self.encoded_limit:
            raise ContentSizeLimitError(
                f"{label} exceeds maximum encoded size {self.encoded_limit} bytes"
            )
        try:
            node = json.loads(encoded)
        except (json.JSONDecodeError, RecursionError, ValueError, TypeError) as exc:
            raise ContentIntegrityError(f"{label} is not valid encoded content") from exc
        try:
            if _canonical(node) != encoded:
                raise ContentIntegrityError(f"{label} is not canonically encoded")
        except ValueError as exc:
            if isinstance(exc, ContentIntegrityError):
                raise
            raise ContentIntegrityError(f"{label} is not strict JSON") from exc
        if type(node) is not list:
            raise ContentIntegrityError(f"{label} has an invalid typed node")
        return node

    def measure(self, node: list[Any], depth: int = 0) -> int:
        if depth > self.max_depth:
            raise ContentIntegrityError(
                f"encoded content exceeds maximum depth {self.max_depth}"
            )
        if not node or type(node[0]) is not str:
            raise ContentIntegrityError("encoded content has an invalid typed node")
        tag = node[0]
        if tag == "null" and len(node) == 1:
            return 4
        if tag == "bool" and len(node) == 2 and type(node[1]) is bool:
            return 4 if node[1] else 5
        if tag == "int" and len(node) == 2 and type(node[1]) is int:
            return _canonical_bytes(node[1])
        if (
            tag == "float"
            and len(node) == 2
            and type(node[1]) is float
            and math.isfinite(node[1])
        ):
            return _canonical_bytes(node[1])
        if tag == "string" and len(node) == 2 and type(node[1]) is str:
            return _canonical_bytes(node[1])
        if tag == "ref":
            return self._reference_fields(node)[1]
        if tag == "list" and len(node) == 2 and type(node[1]) is list:
            total = 2
            for index, child in enumerate(node[1]):
                if type(child) is not list:
                    raise ContentIntegrityError("list contains an invalid typed node")
                total += self.measure(child, depth + 1) + (1 if index else 0)
                self._check_bound(total)
            return total
        if tag == "dict" and len(node) == 2 and type(node[1]) is list:
            total = 2
            previous: str | None = None
            for index, entry in enumerate(node[1]):
                if (
                    type(entry) is not list
                    or len(entry) != 2
                    or type(entry[0]) is not str
                    or type(entry[1]) is not list
                ):
                    raise ContentIntegrityError("object contains an invalid entry")
                key = entry[0]
                if previous is not None and key <= previous:
                    raise ContentIntegrityError(
                        "object keys are duplicated or not canonically ordered"
                    )
                previous = key
                total += _canonical_bytes(key) + 1
                total += self.measure(entry[1], depth + 1) + (1 if index else 0)
                self._check_bound(total)
            return total
        raise ContentIntegrityError(f"encoded content has invalid node tag {tag!r}")

    def decode(self, node: list[Any], depth: int = 0) -> Any:
        logical_bytes = self.measure(node, depth)
        self._check_bound(logical_bytes)
        tag = node[0]
        if tag == "null":
            return None
        if tag in {"bool", "int", "float", "string"}:
            return node[1]
        if tag == "ref":
            digest, expected = self._reference_fields(node)
            return self._load(digest, expected, depth)
        if tag == "list":
            return [self.decode(child, depth + 1) for child in node[1]]
        return {entry[0]: self.decode(entry[1], depth + 1) for entry in node[1]}

    def _load(self, digest: str, expected: int, depth: int) -> Any:
        self._check_bound(expected)
        if digest in self.active:
            raise ContentIntegrityError(f"content object cycle detected at {digest}")
        if len(self.active) >= self.max_depth:
            raise ContentIntegrityError(
                f"content reference chain exceeds maximum depth {self.max_depth}"
            )
        verified = self.verified.get(digest)
        if verified is None:
            row = self.connection.execute(
                "SELECT logical_bytes,length(CAST(encoded AS BLOB)) "
                "FROM sdk_content_objects WHERE digest=?",
                (digest,),
            ).fetchone()
            if row is None:
                raise ContentIntegrityError(f"content object {digest} is missing")
            logical_bytes, encoded_bytes = row[0], row[1]
            if (
                type(logical_bytes) is not int
                or logical_bytes < 0
                or type(encoded_bytes) is not int
                or encoded_bytes < 0
            ):
                raise ContentIntegrityError(
                    f"content object {digest} has invalid metadata"
                )
            if logical_bytes != expected:
                raise ContentIntegrityError(
                    f"content object {digest} logical length does not match reference"
                )
            if encoded_bytes > self.encoded_limit:
                raise ContentSizeLimitError(
                    f"content object {digest} exceeds maximum encoded size "
                    f"{self.encoded_limit} bytes"
                )
            if self.read_budget is not None:
                self.read_budget.consume(encoded_bytes)
            body = self.connection.execute(
                "SELECT encoded FROM sdk_content_objects WHERE digest=? "
                "AND length(CAST(encoded AS BLOB))<=?",
                (digest, self.encoded_limit),
            ).fetchone()
            if body is None or type(body[0]) is not str:
                raise ContentIntegrityError(
                    f"content object {digest} has invalid encoded content"
                )
            encoded = body[0]
            node = self.parse(encoded, f"content object {digest}")
            if _object_digest(encoded) != digest:
                raise ContentIntegrityError(
                    f"content object {digest} failed digest verification"
                )
            measured = self.measure(node, depth)
            if measured != logical_bytes:
                raise ContentIntegrityError(
                    f"content object {digest} logical length metadata is invalid"
                )
            verified = (node, logical_bytes)
            self.verified[digest] = verified
        elif verified[1] != expected:
            raise ContentIntegrityError(
                f"content object {digest} logical length does not match reference"
            )
        self.active.add(digest)
        try:
            return self.decode(verified[0], depth)
        finally:
            self.active.remove(digest)

    def _reference_fields(self, node: list[Any]) -> tuple[str, int]:
        if (
            len(node) != 3
            or type(node[1]) is not str
            or _DIGEST_RE.fullmatch(node[1]) is None
            or type(node[2]) is not int
            or node[2] < 0
        ):
            raise ContentIntegrityError("encoded content has an invalid reference")
        return node[1], node[2]

    def _check_bound(self, logical_bytes: int) -> None:
        if logical_bytes > self.maximum:
            raise ContentSizeLimitError(
                f"content is {logical_bytes} bytes; maximum is {self.maximum}"
            )


def _legacy_measure(value: Any, maximum: int, max_depth: int, depth: int = 0) -> int:
    if depth > max_depth:
        raise ContentIntegrityError(f"legacy JSON exceeds maximum depth {max_depth}")
    if value is None:
        size = 4
    elif type(value) is bool:
        size = 4 if value else 5
    elif type(value) in {int, float, str}:
        try:
            size = _canonical_bytes(value)
        except ValueError as exc:
            raise ContentIntegrityError("legacy value is not strict JSON") from exc
    elif type(value) is list:
        size = 2
        for index, child in enumerate(value):
            size += _legacy_measure(child, maximum, max_depth, depth + 1)
            size += 1 if index else 0
            if size > maximum:
                break
    elif type(value) is dict and all(type(key) is str for key in value):
        size = 2
        for index, key in enumerate(sorted(value)):
            size += _canonical_bytes(key) + 1
            size += _legacy_measure(value[key], maximum, max_depth, depth + 1)
            size += 1 if index else 0
            if size > maximum:
                break
    else:
        raise ContentIntegrityError("legacy value is not strict JSON")
    if size > maximum:
        raise ContentSizeLimitError(f"content is {size} bytes; maximum is {maximum}")
    return size


def decode_value(
    connection: sqlite3.Connection,
    encoded: str,
    *,
    max_logical_bytes: int = MAX_LOGICAL_BYTES,
    max_encoded_bytes: int = MAX_ENCODED_BYTES,
    max_depth: int = MAX_DEPTH,
    read_budget: ContentReadBudget | None = None,
) -> Any:
    """Decode a codec value, or plain legacy JSON, under logical and wire limits."""

    maximum = _positive_integer(max_logical_bytes, "max_logical_bytes")
    requested_encoded = _positive_integer(max_encoded_bytes, "max_encoded_bytes")
    encoded_limit = _encoded_limit(maximum, requested_encoded)
    depth_limit = _positive_integer(max_depth, "max_depth")
    if type(encoded) is not str:
        raise TypeError("encoded must be a string")
    if read_budget is not None:
        if not isinstance(read_budget, ContentReadBudget):
            raise TypeError("read_budget must be a ContentReadBudget")
        read_budget.consume(_utf8_size_with_limit(encoded, encoded_limit))
    if not encoded.startswith(CONTENT_PREFIX):
        if _utf8_size_with_limit(encoded, encoded_limit) > encoded_limit:
            raise ContentSizeLimitError(
                f"legacy encoded content exceeds maximum encoded size {encoded_limit} bytes"
            )
        try:
            value = json.loads(encoded)
        except (json.JSONDecodeError, RecursionError, ValueError, TypeError) as exc:
            raise ContentIntegrityError("legacy value is not valid JSON") from exc
        _legacy_measure(value, maximum, depth_limit)
        return value

    if _utf8_size_with_limit(encoded, encoded_limit) > encoded_limit:
        raise ContentSizeLimitError(
            f"encoded root exceeds maximum encoded size {encoded_limit} bytes"
        )
    decoder = _Decoder(
        connection, maximum, depth_limit, encoded_limit=encoded_limit, read_budget=read_budget
    )
    root_encoded = encoded[len(CONTENT_PREFIX) :]
    root = decoder.parse(root_encoded, "encoded root")
    decoder._check_bound(decoder.measure(root))
    return decoder.decode(root)


__all__ = [
    "CONTENT_SCHEMA",
    "CONTENT_PREFIX",
    "DEFAULT_THRESHOLD",
    "MAX_LOGICAL_BYTES",
    "MAX_ENCODED_BYTES",
    "MAX_DEPTH",
    "ContentIntegrityError",
    "ContentSizeLimitError",
    "ContentReadBudget",
    "encode_value",
    "decode_value",
]
