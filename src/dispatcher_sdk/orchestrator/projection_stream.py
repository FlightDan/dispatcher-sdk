"""Bounded, snapshot-scoped direct reads of application projection content.

References are used solely as existing storage lookup keys. This reader adds no
content identity verification. A missing or oversized node stops the stream;
consumers must not regard its prefix as a complete projection.
"""
from __future__ import annotations

import codecs
import json
from contextlib import closing

from ..content import CONTENT_PREFIX
from .contracts import OrchestrationError, canonical, identifier, integer

STREAM_POINTER_PREFIX = "sdk-projection-stream-v1:"


def iter_installed_projection(orchestrator, run_id, *, revision, storage, credential):
    """Read an installed current or historical stream under host retention proof.

    The host verifier receives the actual storage object and must authenticate
    it against the pointer and continuously protect its bytes against mutation
    and deletion. A caller must
    exhaust the iterator to establish that the complete stream was read.
    """
    identifier(run_id, "run_id")
    integer(revision, "revision")
    from .projection_storage import ProjectionStorage, MAX_PAGE_BYTES
    if type(storage) is not ProjectionStorage:
        raise OrchestrationError("identified projection storage is required")
    verifier = getattr(orchestrator, "projection_verifier", None)
    if not callable(verifier):
        raise OrchestrationError("host projection retention verifier is required")
    connection = orchestrator._connect()
    try:
        connection.execute("BEGIN")
        if connection.execute("SELECT 1 FROM sdk_run_revisions WHERE run_id=? AND revision=?", (run_id, revision)).fetchone() is None:
            raise OrchestrationError("projection revision is unavailable")
        row = connection.execute("SELECT CASE WHEN length(CAST(p.pointer AS BLOB))<=65536 THEN p.pointer END "
            "FROM sdk_streamed_projection_pointers p WHERE p.run_id=? AND p.revision=(SELECT MAX(h.revision) FROM sdk_run_history h "
            "WHERE h.run_id=? AND h.section='root' AND h.item_key='application_state' AND h.revision<=?)", (run_id, run_id, revision)).fetchone()
        identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
        if identity is None:
            raise OrchestrationError("Orchestrator identity is unavailable")
        if row is None or row[0] is None or not row[0].startswith(STREAM_POINTER_PREFIX):
            raise OrchestrationError("streamed projection pointer is unavailable")
        pointer = json.loads(row[0][len(STREAM_POINTER_PREFIX):])
        if (type(pointer) is not dict or set(pointer) != {"stream_id", "binding", "total_bytes", "store_id", "incarnation"} or
                type(pointer["stream_id"]) is not str or type(pointer["binding"]) is not dict or
                type(pointer["total_bytes"]) is not int or pointer["total_bytes"] < 0 or
                type(pointer["store_id"]) is not str or type(pointer["incarnation"]) is not str):
            raise OrchestrationError("streamed projection pointer is invalid")
        # The pointer and Orchestrator identity were read in one snapshot. Do
        # not retain that SQLite snapshot while the consumer streams bytes.
        connection.rollback()
        def authorize():
            claim = verifier(credential, storage)
            if (type(claim) is not dict or claim.get("retained_immutable") is not True or
                    canonical(claim.get("pointer")) != canonical(pointer) or
                    claim.get("run_id") != run_id or claim.get("revision") != revision or
                    (claim.get("orchestrator_store_id"), claim.get("orchestrator_incarnation")) != tuple(identity)):
                raise OrchestrationError("projection retention authority is unknown")
        cursor, size = -1, 0
        while True:
            authorize()
            batch = storage.read(pointer["stream_id"], after=cursor, limit=1)
            if (not batch["complete"] or batch["total_bytes"] != pointer["total_bytes"] or
                    batch["stored_bytes"] != pointer["total_bytes"] or
                    (batch.get("store_id"), batch.get("incarnation")) != (pointer["store_id"], pointer["incarnation"]) or
                    canonical(batch["binding"]) != canonical(pointer["binding"]) or len(batch["pages"]) != 1):
                raise OrchestrationError("installed projection stream is incomplete or changed")
            page = batch["pages"][0]
            if (type(page.get("data")) is not bytes or len(page["data"]) > MAX_PAGE_BYTES or
                    type(page.get("complete")) is not bool or page["complete"] != (not batch["has_more"])):
                raise OrchestrationError("installed projection page exceeds bounded limit")
            size += len(page["data"])
            yield page["data"]
            cursor = batch["cursor"]
            if not batch["has_more"]:
                if not page["complete"] or size != pointer["total_bytes"]:
                    raise OrchestrationError("installed projection stream is incomplete")
                authorize()
                break
    finally:
        connection.rollback()
        connection.close()


def compare_projection_stream(orchestrator, run_id, *, expected_revision, storage,
                              stream_id, expected_binding, max_node_bytes=262144,
                              source_read_credential=None):
    """Compare complete direct stream bytes with one Run projection snapshot.

    This is a content comparison, not authority or storage-isolation evidence.
    The host must authenticate the binding and retain immutable stream storage.
    """
    from .projection_storage import ProjectionStorage, MAX_PAGE_BYTES
    if type(storage) is not ProjectionStorage:
        raise OrchestrationError("identified projection storage is required")
    info = storage.inspect(stream_id)
    if (type(expected_binding) is not dict or canonical(info["binding"]) != canonical(expected_binding) or
            not info["complete"] or info["stored_bytes"] != info["total_bytes"]):
        raise OrchestrationError("complete bound projection stream is required")
    with closing(orchestrator._connect()) as probe:
        has_pointers = probe.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sdk_streamed_projection_pointers'").fetchone()
        row = None if has_pointers is None else probe.execute(
            "SELECT 1 FROM sdk_streamed_projection_pointers p WHERE p.run_id=? AND p.revision=(SELECT MAX(h.revision) FROM sdk_run_history h WHERE h.run_id=? AND h.section='root' AND h.item_key='application_state' AND h.revision<=?)",
            (run_id, run_id, expected_revision)).fetchone()
    if row is not None:
        if source_read_credential is None:
            raise OrchestrationError("host authority for the installed source stream is required")
        fragments = iter(iter_installed_projection(orchestrator, run_id, revision=expected_revision,
                                                   storage=storage, credential=source_read_credential))
    else:
        fragments = iter(iter_application_projection(orchestrator, run_id,
                         expected_revision=expected_revision, max_node_bytes=max_node_bytes))
    pending = b""
    count, cursor, final = 0, -1, False
    try:
        while True:
            batch = storage.read(stream_id, after=cursor, limit=1)
            if (canonical(batch["binding"]) != canonical(expected_binding) or not batch["complete"] or
                    batch["total_bytes"] != info["total_bytes"] or batch["stored_bytes"] != info["total_bytes"] or
                    (batch.get("store_id"), batch.get("incarnation")) != (info.get("store_id"), info.get("incarnation")) or
                    len(batch["pages"]) != 1):
                raise OrchestrationError("projection stream is incomplete or changed")
            page = batch["pages"][0]
            data = page["data"]
            if (type(data) is not bytes or len(data) > MAX_PAGE_BYTES or type(page.get("complete")) is not bool or
                    page["complete"] != (not batch["has_more"])):
                raise OrchestrationError("projection stream page exceeds bounded limit")
            offset = 0
            while offset < len(data):
                if not pending:
                    try:
                        fragment = next(fragments)
                        pending = fragment if isinstance(fragment, bytes) else fragment.encode("utf-8")
                    except StopIteration:
                        raise OrchestrationError("projection stream differs") from None
                    if not pending:
                        continue
                size = min(len(pending), len(data) - offset)
                if pending[:size] != data[offset:offset + size]:
                    raise OrchestrationError("projection stream differs")
                pending = pending[size:]
                offset += size
            count += len(data)
            cursor = batch["cursor"]
            if not batch["has_more"]:
                final = page["complete"]
                break
        if pending or next(fragments, None) is not None or not final or count != info["total_bytes"]:
            raise OrchestrationError("projection stream differs or is incomplete")
    finally:
        fragments.close()
    return {"stream_id": stream_id, "source_revision": expected_revision,
            "total_bytes": count, "binding": expected_binding,
            "store_id": info["store_id"], "incarnation": info["incarnation"]}


def iter_application_projection(orchestrator, run_id, *, expected_revision, max_node_bytes=262144):
    """Yield direct JSON fragments from one stable SQLite read snapshot.

    Memory is bounded per stored node, not by the total projection. A single
    encoded node exceeding the budget is unsupported. The iterator must be
    exhausted before the caller treats the projection as complete.
    """
    identifier(run_id, "run_id")
    integer(expected_revision, "expected_revision")
    if type(max_node_bytes) is not int or not 1024 <= max_node_bytes <= 1048576:
        raise OrchestrationError("invalid projection node budget")
    connection = orchestrator._connect()
    try:
        connection.execute("BEGIN")
        revision = connection.execute("SELECT revision FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()
        if revision is None or revision[0] != expected_revision:
            raise OrchestrationError("projection source revision changed")
        pointer_table = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sdk_streamed_projection_pointers'").fetchone()
        direct_mode = ("EXISTS(SELECT 1 FROM sdk_streamed_projection_pointers p WHERE p.run_id=i.run_id)"
                       if pointer_table else "0")
        meta = connection.execute(
            "SELECT length(CAST(value AS BLOB)),substr(value,1,?), " + direct_mode +
            " FROM sdk_run_items i WHERE run_id=? AND section='root' AND item_key='application_state'",
            (len(CONTENT_PREFIX), run_id),
        ).fetchone()
        if meta is not None and meta[0] > max_node_bytes and meta[1] != CONTENT_PREFIX and meta[2]:
            if meta[0] > 64 * 1024 * 1024:
                raise OrchestrationError("projection root exceeds the stream budget")
            from .projection_json import _Validator, ProjectionJSONError
            validator = _Validator(64)
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            try:
                offset = 1
                while offset <= meta[0]:
                    row = connection.execute(
                        "SELECT substr(CAST(value AS BLOB),?,?) FROM sdk_run_items "
                        "WHERE run_id=? AND section='root' AND item_key='application_state'",
                        (offset, max_node_bytes, run_id),
                    ).fetchone()
                    chunk = None if row is None else row[0]
                    if type(chunk) is not bytes or not chunk:
                        raise OrchestrationError("projection root is incomplete")
                    validator.feed(decoder.decode(chunk))
                    yield chunk
                    offset += len(chunk)
                validator.feed(decoder.decode(b"", final=True))
                validator.finish()
            except (UnicodeError, ProjectionJSONError) as error:
                raise OrchestrationError("projection root is invalid") from error
            return
        root = connection.execute("SELECT value FROM sdk_run_items WHERE run_id=? AND section='root' "
                                  "AND item_key='application_state' AND length(CAST(value AS BLOB))<=?",
                                  (run_id, max_node_bytes)).fetchone()
        if root is None:
            raise OrchestrationError("projection root is missing or exceeds the node budget")
        encoded = root[0]
        if not encoded.startswith(CONTENT_PREFIX):
            # Legacy inline JSON is already bounded by the root read.
            yield canonical(json.loads(encoded))
            return
        active = set()
        def walk(node, depth):
            if depth > 100 or type(node) is not list or not node or type(node[0]) is not str:
                raise OrchestrationError("projection node is invalid or too deep")
            tag = node[0]
            if tag == "null" and len(node) == 1:
                yield "null"
            elif tag in ("bool", "int", "float", "string") and len(node) == 2:
                types = {"bool": bool, "int": int, "float": float, "string": str}
                if type(node[1]) is not types[tag]:
                    raise OrchestrationError("projection scalar is invalid")
                yield canonical(node[1])
            elif tag == "ref" and len(node) == 3 and type(node[1]) is str:
                key = node[1]
                if key in active:
                    raise OrchestrationError("projection reference cycle")
                row = connection.execute("SELECT encoded FROM sdk_content_objects WHERE digest=? "
                    "AND length(CAST(encoded AS BLOB))<=?", (key, max_node_bytes)).fetchone()
                if row is None:
                    raise OrchestrationError("projection object is missing or exceeds the node budget")
                active.add(key)
                try:
                    yield from walk(json.loads(row[0]), depth + 1)
                finally:
                    active.remove(key)
            elif tag == "list" and len(node) == 2 and type(node[1]) is list:
                yield "["
                for index, child in enumerate(node[1]):
                    if index:
                        yield ","
                    yield from walk(child, depth + 1)
                yield "]"
            elif tag == "dict" and len(node) == 2 and type(node[1]) is list:
                yield "{"
                previous = None
                for index, entry in enumerate(node[1]):
                    if (type(entry) is not list or len(entry) != 2 or type(entry[0]) is not str or
                            (previous is not None and entry[0] <= previous)):
                        raise OrchestrationError("projection mapping is invalid or unordered")
                    previous = entry[0]
                    if index:
                        yield ","
                    yield canonical(entry[0])
                    yield ":"
                    yield from walk(entry[1], depth + 1)
                yield "}"
            else:
                raise OrchestrationError("projection node is invalid")
        yield from walk(json.loads(encoded[len(CONTENT_PREFIX):]), 0)
    finally:
        connection.rollback()
        connection.close()
