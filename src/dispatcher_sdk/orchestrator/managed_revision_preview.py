"""Conservative, handler-free planning for managed Run revisions.

This module only compares declarations and computes an invalidation closure. It
does not read persisted state, authorize work, prepare a revision, or make a
commit decision. A listed reuse candidate still needs authoritative rechecks by
the caller before any future revision protocol could reuse it.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict, deque
from typing import Any


class ManagedRevisionPreviewError(ValueError):
    """A preview input is not a strict declaration or relation record."""


def _identifier(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise ManagedRevisionPreviewError(f"{label} must be a non-empty string ID")
    return value


def _strict_json(value: Any, label: str) -> Any:
    """Return a detached JSON value, rejecting non-finite and exotic values."""
    def validate(item: Any, active: set[int]) -> None:
        if item is None or type(item) in {bool, int, str}:
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise ManagedRevisionPreviewError(f"{label} must be finite strict JSON")
            return
        if type(item) not in {list, dict}:
            raise ManagedRevisionPreviewError(f"{label} must be strict JSON")
        identity = id(item)
        if identity in active:
            raise ManagedRevisionPreviewError(f"{label} must not contain a cyclic reference")
        active.add(identity)
        try:
            if type(item) is list:
                for child in item:
                    validate(child, active)
            else:
                if any(type(key) is not str for key in item):
                    raise ManagedRevisionPreviewError(
                        f"{label} object keys must be strings"
                    )
                for child in item.values():
                    validate(child, active)
        finally:
            active.remove(identity)

    try:
        validate(value, set())
    except RecursionError as error:
        raise ManagedRevisionPreviewError(f"{label} exceeds strict JSON nesting limits") from error
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        )
        return json.loads(encoded)
    except (OverflowError, RecursionError, TypeError, ValueError) as error:
        raise ManagedRevisionPreviewError(f"{label} must be finite strict JSON") from error


def _task_graph(value: Any, label: str) -> dict[str, dict[str, Any]]:
    if type(value) is not list:
        raise ManagedRevisionPreviewError(f"{label} must be a list of task declarations")
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(value):
        task = _strict_json(raw, f"{label}[{index}]")
        if type(task) is not dict:
            raise ManagedRevisionPreviewError(f"{label}[{index}] must be an object")
        task_id = _identifier(task.get("task_id"), f"{label}[{index}].task_id")
        if task_id in result:
            raise ManagedRevisionPreviewError(f"{label} contains duplicate task ID {task_id!r}")
        dependencies = task.get("dependencies")
        if type(dependencies) is not list:
            raise ManagedRevisionPreviewError(
                f"{label}[{index}].dependencies must be a list of task IDs"
            )
        normalized = [_identifier(item, f"{label}[{index}].dependencies")
                      for item in dependencies]
        if len(normalized) != len(set(normalized)):
            raise ManagedRevisionPreviewError(
                f"{label}[{index}].dependencies must not contain duplicates"
            )
        task["dependencies"] = sorted(normalized)
        result[task_id] = task
    return result


def _relation_list(value: Any, *, label: str, fields: tuple[str, ...],
                   id_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if type(value) is not list:
        raise ManagedRevisionPreviewError(f"{label} must be a list or None")
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        relation = _strict_json(raw, f"{label}[{index}]")
        if type(relation) is not dict or set(relation) != set(fields):
            raise ManagedRevisionPreviewError(
                f"{label}[{index}] must contain exactly {', '.join(fields)}"
            )
        clean = dict(relation)
        for field in id_fields:
            clean[field] = _identifier(clean[field], f"{label}[{index}].{field}")
        if type(clean["registered"]) is not bool:
            raise ManagedRevisionPreviewError(
                f"{label}[{index}].registered must be a boolean"
            )
        normalized.append(clean)
    return sorted(normalized, key=lambda item: json.dumps(
        item, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def _reuse_evidence(value: Any) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    evidence = _strict_json(value, "reuse_evidence")
    if type(evidence) is not dict:
        raise ManagedRevisionPreviewError("reuse_evidence must be an object keyed by task ID")
    result: dict[str, dict[str, Any]] = {}
    for task_id, raw in evidence.items():
        _identifier(task_id, "reuse_evidence task ID")
        if type(raw) is not dict:
            raise ManagedRevisionPreviewError(
                f"reuse_evidence[{task_id!r}] must be an object"
            )
        result[task_id] = raw
    return result


def _cycles(graph: dict[str, dict[str, Any]]) -> list[list[str]]:
    """Return strongly connected task groups that contain a directed cycle."""
    nodes = set(graph)
    edges = {
        task_id: sorted(dep for dep in task["dependencies"] if dep in nodes)
        for task_id, task in graph.items()
    }
    reverse: dict[str, list[str]] = {node: [] for node in nodes}
    for node, dependencies in edges.items():
        for dependency in dependencies:
            reverse[dependency].append(node)
    for children in reverse.values():
        children.sort()

    visited: set[str] = set()
    order: list[str] = []
    for start in sorted(nodes):
        if start in visited:
            continue
        visited.add(start)
        stack = [(start, iter(edges[start]))]
        while stack:
            node, children = stack[-1]
            try:
                child = next(children)
            except StopIteration:
                order.append(node)
                stack.pop()
                continue
            if child in visited:
                continue
            visited.add(child)
            stack.append((child, iter(edges[child])))

    visited.clear()
    components: list[list[str]] = []
    for start in reversed(order):
        if start in visited:
            continue
        component: list[str] = []
        stack = [start]
        visited.add(start)
        while stack:
            node = stack.pop()
            component.append(node)
            for child in reverse[node]:
                if child not in visited:
                    visited.add(child)
                    stack.append(child)
        component.sort()
        if len(component) > 1 or component[0] in edges[component[0]]:
            components.append(component)
    return sorted(components)


def _closure(seed_ids: set[str], edges: dict[str, set[str]]) -> set[str]:
    affected = set(seed_ids)
    pending = deque(sorted(seed_ids))
    while pending:
        source = pending.popleft()
        for consumer in sorted(edges.get(source, ())):
            if consumer not in affected:
                affected.add(consumer)
                pending.append(consumer)
    return affected


def _valid_reuse_proof(value: dict[str, Any]) -> tuple[bool, list[str]]:
    required = ("result_id", "content_identity", "source_generation",
                "compatible", "application_valid")
    missing = [field for field in required if field not in value]
    for field in ("result_id", "content_identity"):
        if field in value and (type(value[field]) is not str or not value[field].strip()):
            missing.append(field)
    if "source_generation" in value and (
            type(value["source_generation"]) is not int or value["source_generation"] < 0):
        missing.append("source_generation")
    for field in ("compatible", "application_valid"):
        if field in value and type(value[field]) is not bool:
            missing.append(field)
    if value.get("compatible") is not True:
        missing.append("compatible=true")
    if value.get("application_valid") is not True:
        missing.append("application_valid=true")
    return not missing, sorted(set(missing))


def preview_managed_revision(
    old_tasks: Any,
    new_tasks: Any,
    *,
    changed_task_ids: Any,
    wait_relations: Any = None,
    artifact_relations: Any = None,
    reuse_evidence: Any = None,
) -> dict[str, Any]:
    """Build a deterministic invalidation preview without touching live state.

    ``old_tasks`` and ``new_tasks`` are lists of strict JSON objects. Each task
    has a non-empty ``task_id`` and a ``dependencies`` list; other JSON fields
    are compared as part of the declaration. A wait relation has exactly
    ``wait_id``, ``parent_task_id``, ``waited_task_id``, and ``registered``.
    An artifact relation has exactly ``artifact_id``, ``producer_task_id``,
    ``consumer_task_id``, and ``registered``. Pass an empty list when the
    corresponding relation inventory was checked and none exist; ``None``
    means the evidence is unavailable and forces a conservative full rebuild.

    Reuse evidence is an application supplied claim keyed by task ID. Complete
    claims are reported only as candidates and are never treated as authority.
    """
    old = _task_graph(old_tasks, "old_tasks")
    new = _task_graph(new_tasks, "new_tasks")
    if type(changed_task_ids) is not list:
        raise ManagedRevisionPreviewError("changed_task_ids must be a list of task IDs")
    changed_values = [_identifier(value, "changed_task_ids") for value in changed_task_ids]
    if len(changed_values) != len(set(changed_values)):
        raise ManagedRevisionPreviewError("changed_task_ids must not contain duplicates")
    explicit_changed = set(changed_values)
    waits_available = wait_relations is not None
    artifacts_available = artifact_relations is not None
    waits = _relation_list(
        wait_relations, label="wait_relations",
        fields=("wait_id", "parent_task_id", "waited_task_id", "registered"),
        id_fields=("wait_id", "parent_task_id", "waited_task_id"),
    )
    artifacts = _relation_list(
        artifact_relations, label="artifact_relations",
        fields=("artifact_id", "producer_task_id", "consumer_task_id", "registered"),
        id_fields=("artifact_id", "producer_task_id", "consumer_task_id"),
    )
    reuse = _reuse_evidence(reuse_evidence)

    old_ids, new_ids = set(old), set(new)
    all_ids = old_ids | new_ids
    blockers: list[dict[str, Any]] = []
    derived_changed = (old_ids ^ new_ids) | {
        task_id for task_id in old_ids & new_ids
        if old[task_id] != new[task_id]
    }
    changed = explicit_changed | derived_changed
    unknown_changed = explicit_changed - all_ids
    for task_id in sorted(unknown_changed):
        blockers.append({"code": "unknown_changed_task", "task_id": task_id})

    edges: dict[str, set[str]] = defaultdict(set)
    seed_ids = set(changed & all_ids)
    for graph_name, graph in (("old", old), ("new", new)):
        for task_id, task in graph.items():
            for dependency in task["dependencies"]:
                if dependency not in graph:
                    code = "deleted_dependency" if dependency in old_ids else "missing_dependency"
                    blockers.append({
                        "code": code, "graph": graph_name,
                        "task_id": task_id, "dependency_task_id": dependency,
                    })
                    if graph_name == "new":
                        seed_ids.add(task_id)
                else:
                    edges[dependency].add(task_id)
        for component in _cycles(graph):
            blockers.append({"code": "task_graph_cycle", "graph": graph_name,
                             "task_ids": component})
            seed_ids.update(component)

    for relation in waits:
        parent = relation["parent_task_id"]
        waited = relation["waited_task_id"]
        missing = sorted({parent, waited} - all_ids)
        if missing:
            blockers.append({"code": "wait_task_missing", "wait_id": relation["wait_id"],
                             "task_ids": missing})
        if not relation["registered"]:
            blockers.append({"code": "unregistered_wait", "wait_id": relation["wait_id"],
                             "parent_task_id": parent, "waited_task_id": waited})
        # A wait is a dependency from the awaited child to the parent. Include
        # it even when registration is disputed, so known information expands
        # impact instead of narrowing it.
        edges[waited].add(parent)

    for relation in artifacts:
        producer = relation["producer_task_id"]
        consumer = relation["consumer_task_id"]
        missing = sorted({producer, consumer} - all_ids)
        if missing:
            blockers.append({"code": "artifact_task_missing",
                             "artifact_id": relation["artifact_id"], "task_ids": missing})
        if not relation["registered"]:
            blockers.append({"code": "unregistered_artifact_relation",
                             "artifact_id": relation["artifact_id"],
                             "producer_task_id": producer, "consumer_task_id": consumer})
        edges[producer].add(consumer)

    relation_evidence_incomplete = not waits_available or not artifacts_available or any(
        blocker["code"] in {
            "unregistered_wait", "wait_task_missing", "unregistered_artifact_relation",
            "artifact_task_missing",
        }
        for blocker in blockers
    )
    graph_evidence_invalid = any(blocker["code"] in {
        "deleted_dependency", "missing_dependency", "task_graph_cycle",
    } for blocker in blockers)

    affected = _closure(seed_ids, edges)
    if not waits_available:
        blockers.append({"code": "wait_evidence_missing"})
    if not artifacts_available:
        blockers.append({"code": "artifact_evidence_missing"})
    if relation_evidence_incomplete or graph_evidence_invalid or unknown_changed:
        # Unknown relations or an invalid target graph prevent proving that an
        # apparently disconnected task is independent of the changed work.
        affected.update(new_ids)

    required_proof_fields = ["application_valid", "compatible", "content_identity",
                             "result_id", "source_generation"]
    candidates: list[dict[str, Any]] = []
    unproved: list[dict[str, Any]] = []
    must_recompute = set(affected & new_ids) | (new_ids - old_ids)
    for task_id in sorted((old_ids & new_ids) - must_recompute):
        proof = reuse.get(task_id)
        if proof is None:
            unproved.append({"task_id": task_id, "missing": required_proof_fields})
            must_recompute.add(task_id)
            continue
        valid, missing = _valid_reuse_proof(proof)
        if not valid:
            unproved.append({"task_id": task_id, "missing": missing})
            must_recompute.add(task_id)
            continue
        candidates.append({"task_id": task_id, "evidence": proof})
    if unproved:
        blockers.append({"code": "reuse_unproved", "tasks": unproved})

    impact_complete = not relation_evidence_incomplete and not graph_evidence_invalid and not unknown_changed
    evidence_complete = impact_complete and not unproved

    impacted_sorted = sorted(affected & all_ids)
    recompute_sorted = sorted(must_recompute)
    retired = sorted(old_ids - new_ids)
    # Normalize blocker order and remove duplicate records without depending on
    # caller order for relations or task declarations.
    unique_blockers = {json.dumps(item, sort_keys=True, ensure_ascii=False,
                                  separators=(",", ":")): item for item in blockers}
    ordered_blockers = [unique_blockers[key] for key in sorted(unique_blockers)]
    target_order = {task_id: index for index, task_id in enumerate(sorted(new_ids))}
    candidates.sort(key=lambda item: target_order[item["task_id"]])

    identity = {
        "old_tasks": [old[key] for key in sorted(old)],
        "new_tasks": [new[key] for key in sorted(new)],
        "changed_task_ids": sorted(changed),
        "wait_relations": waits if waits_available else None,
        "artifact_relations": artifacts if artifacts_available else None,
        "reuse_evidence": reuse,
    }
    identity_json = json.dumps(identity, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": 1,
        "kind": "managed_revision_preview",
        "preview_digest": hashlib.sha256(identity_json.encode("utf-8")).hexdigest(),
        "previewable": True,
        "commit_safe": False,
        "impact_complete": impact_complete,
        "evidence_complete": evidence_complete,
        "source_task_ids": sorted(old_ids),
        "target_task_ids": sorted(new_ids),
        "changed_task_ids": sorted(changed),
        "impacted_task_ids": impacted_sorted,
        "must_recompute_task_ids": recompute_sorted,
        "retired_task_ids": retired,
        "reuse_candidates": candidates,
        "blockers": ordered_blockers,
    }
