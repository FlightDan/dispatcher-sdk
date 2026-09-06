"""Mechanical operation validation. No application routing or policy lives here."""

from __future__ import annotations

from .contracts import OrchestrationError, TERMINAL, RUN_TERMINAL, attempt, identifier


def _dependencies(tasks: dict, task_id: str, values: object) -> list:
    if type(values) is not list or any(type(v) is not str for v in values):
        raise OrchestrationError("dependencies must be task identifiers")
    if len(set(values)) != len(values) or task_id in values:
        raise OrchestrationError("duplicate or self dependency")
    if any(v not in tasks for v in values):
        raise OrchestrationError("unknown dependency; add predecessors first")
    def reaches(current: str, seen: set) -> bool:
        if current == task_id:
            return True
        if current in seen:
            return False
        seen.add(current)
        return any(reaches(v, seen) for v in tasks[current]["dependencies"])
    if any(reaches(v, set()) for v in values):
        raise OrchestrationError("dependency cycle")
    return list(values)


def reduce_operation(state: dict, op: dict) -> list[dict]:
    """Mutate a private transaction-local snapshot; return durable delivery intents."""
    if state["state"] != "running":
        raise OrchestrationError("run is terminal")
    kind = op["kind"]
    tasks = state["tasks"]
    if kind == "add_task":
        task_id = op["task_id"]
        if task_id in tasks:
            raise OrchestrationError("task already exists")
        deps = _dependencies(tasks, task_id, op.get("dependencies", []))
        tasks[task_id] = {"task_id": task_id, "dependencies": deps,
                          "attempts": [attempt(op["command"])]}
    elif kind in {"dispatch", "new_attempt", "cancel", "set_dependencies"}:
        task = tasks.get(op["task_id"])
        if task is None:
            raise OrchestrationError("unknown task")
        current = task["attempts"][-1]
        if kind == "set_dependencies":
            if len(task["attempts"]) != 1 or current["state"] != "planned":
                raise OrchestrationError("dispatched task dependencies are immutable")
            task["dependencies"] = _dependencies(tasks, op["task_id"], op["dependencies"])
        elif kind == "new_attempt":
            if current["state"] not in TERMINAL:
                raise OrchestrationError("settle or cancel the current attempt first")
            task["attempts"].append(attempt(op["command"]))
        elif kind == "dispatch":
            if current["state"] != "planned":
                raise OrchestrationError("attempt already dispatched or cancelled")
            # Completion is mechanical; the application decides which outcomes allow progress.
            if any(tasks[v]["attempts"][-1]["state"] not in TERMINAL
                   for v in task["dependencies"]):
                raise OrchestrationError("dependencies have not settled")
            current["state"] = "pending_dispatch"
            current["dispatched"] = True
            current["dependency_attempts"] = {
                value: len(tasks[value]["attempts"]) - 1 for value in task["dependencies"]}
            return [{"kind": "dispatch", "execution_id": current["command"]["execution_id"],
                     "command": current["command"]}]
        elif current["state"] == "planned":
            current["state"] = "cancelled"
            current["cancel_reason"] = op["reason"]
        elif current["state"] not in TERMINAL:
            return [{"kind": "cancel", "execution_id": current["command"]["execution_id"],
                     "reason": op["reason"], "command": current["command"]}]
    elif kind == "wait":
        if op["wait_id"] in state["waits"]:
            raise OrchestrationError("wait already exists")
        state["waits"][op["wait_id"]] = {"state": "open", "payload": op.get("payload")}
    elif kind == "release_wait":
        wait = state["waits"].get(op["wait_id"])
        if wait is None or wait["state"] != "open":
            raise OrchestrationError("wait is not open")
        wait["state"] = "released"
    elif kind == "signal":
        if op["signal_id"] in state["signals"]:
            raise OrchestrationError("signal already exists; replay the original command")
        state["signals"][op["signal_id"]] = op["payload"]
    elif kind == "finish":
        if op["state"] not in RUN_TERMINAL:
            raise OrchestrationError("invalid terminal run state")
        if any(t["attempts"][-1]["state"] not in TERMINAL for t in tasks.values()):
            raise OrchestrationError("settle or cancel tasks before finishing")
        if any(w["state"] == "open" for w in state["waits"].values()):
            raise OrchestrationError("release waits before finishing")
        state["state"] = op["state"]
    return []
