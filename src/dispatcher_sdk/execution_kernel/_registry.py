"""Portable canonical fingerprints for exact historical handler registries.

``__execution_kernel_revision__`` may be set to a non-empty immutable string
to bind deployment dependencies that Python code cannot inspect (clients,
native code, modules, locks, and similar state).
"""

from __future__ import annotations

import hashlib
import json
import math
import types
from typing import Any, Callable, Mapping


Handler = Callable[[Any, Any], Any]


def normalize_handlers(handlers: Mapping[Any, Handler]) -> dict[tuple[str, int], Handler]:
    if not isinstance(handlers, Mapping):
        raise TypeError("handlers must be a mapping")
    normalized: dict[tuple[str, int], Handler] = {}
    for raw_key, handler in handlers.items():
        if type(raw_key) is tuple and len(raw_key) == 2:
            handler_id, version = raw_key
        else:
            handler_id, version = raw_key, 1
        if type(handler_id) is not str or not handler_id.strip():
            raise TypeError("handler_id must be a non-empty string")
        if type(version) is not int or version < 1:
            raise TypeError("handler contract version must be a positive integer")
        if not callable(handler):
            raise TypeError(f"handler {(handler_id, version)!r} is not callable")
        key = (handler_id, version)
        if key in normalized:
            raise ValueError(f"duplicate handler binding {key!r}")
        normalized[key] = handler
    return normalized


def _code_constant(value: Any) -> Any:
    if isinstance(value, types.CodeType):
        return {"type": "code", "value": _code(value)}
    if value is None:
        return {"type": "none"}
    if type(value) is bool:
        return {"type": "bool", "value": value}
    if type(value) is int:
        return {"type": "int", "value": str(value)}
    if type(value) is float:
        if not math.isfinite(value):
            raise TypeError("handler code contains a non-finite constant")
        return {"type": "float", "value": value.hex()}
    if type(value) is complex:
        if not math.isfinite(value.real) or not math.isfinite(value.imag):
            raise TypeError("handler code contains a non-finite complex constant")
        return {"type": "complex", "real": value.real.hex(), "imag": value.imag.hex()}
    if type(value) is str:
        return {"type": "str", "value": value}
    if type(value) is bytes:
        return {"type": "bytes", "value": value.hex()}
    if type(value) is tuple:
        return {"type": "tuple", "items": [_code_constant(item) for item in value]}
    if type(value) is frozenset:
        items = [_code_constant(item) for item in value]
        return {"type": "frozenset", "items": _sort_canonical(items)}
    if value is Ellipsis:
        return {"type": "ellipsis"}
    raise TypeError(f"unsupported handler code constant: {type(value).__name__}")


def _code(code: types.CodeType) -> dict[str, Any]:
    """Describe executable code without filename, line, or marshal noise."""

    return {
        "argcount": code.co_argcount,
        "posonlyargcount": getattr(code, "co_posonlyargcount", 0),
        "kwonlyargcount": code.co_kwonlyargcount,
        "nlocals": code.co_nlocals,
        "stacksize": code.co_stacksize,
        "flags": code.co_flags,
        "bytecode": code.co_code.hex(),
        "consts": [_code_constant(value) for value in code.co_consts],
        "names": list(code.co_names),
        "varnames": list(code.co_varnames),
        "freevars": list(code.co_freevars),
        "cellvars": list(code.co_cellvars),
        "exceptiontable": getattr(code, "co_exceptiontable", b"").hex(),
    }


def _referenced_global_names(code: types.CodeType) -> set[str]:
    """Return globals used by this code and any nested code objects."""

    names = set(code.co_names)
    for constant in code.co_consts:
        if isinstance(constant, types.CodeType):
            names.update(_referenced_global_names(constant))
    return names


def _canonical_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sort_canonical(values: list[Any]) -> list[Any]:
    return sorted(values, key=_canonical_text)


def _external_marker(value: Any, explicit: str | None) -> dict[str, str]:
    if explicit is None:
        raise TypeError(
            "handler captures mutable or non-JSON state; set a non-empty "
            "__execution_kernel_revision__ deployment revision"
        )
    value_type = type(value)
    return {
        "type": "deployment-bound-external",
        "class": f"{value_type.__module__}.{value_type.__qualname__}",
    }


def _state(value: Any, explicit: str | None, seen: set[int]) -> Any:
    if value is None:
        return {"type": "none"}
    if type(value) is bool:
        return {"type": "bool", "value": value}
    if type(value) is int:
        return {"type": "int", "value": str(value)}
    if type(value) is float:
        if not math.isfinite(value):
            raise TypeError("handler state contains a non-finite number")
        return {"type": "float", "value": value.hex()}
    if type(value) is str:
        return {"type": "str", "value": value}
    identity = id(value)
    if identity in seen:
        return _external_marker(value, explicit)
    if type(value) in {list, tuple}:
        seen.add(identity)
        try:
            return {
                "type": "list" if type(value) is list else "tuple",
                "items": [_state(item, explicit, seen) for item in value],
            }
        finally:
            seen.remove(identity)
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            return _external_marker(value, explicit)
        seen.add(identity)
        try:
            return {
                "type": "dict",
                "items": [
                    [key, _state(value[key], explicit, seen)] for key in sorted(value)
                ],
            }
        finally:
            seen.remove(identity)
    return _external_marker(value, explicit)


def _explicit_revision(handler: Handler) -> str | None:
    explicit = getattr(handler, "__execution_kernel_revision__", None)
    if explicit is None and isinstance(handler, types.MethodType):
        explicit = getattr(handler.__self__, "__execution_kernel_revision__", None)
    if explicit is not None and (type(explicit) is not str or not explicit.strip()):
        raise TypeError("handler __execution_kernel_revision__ must be a non-empty string")
    return explicit


def _function_manifest(function: types.FunctionType, explicit: str | None) -> dict[str, Any]:
    closure: list[Any] = []
    for cell in function.__closure__ or ():
        try:
            value = cell.cell_contents
        except ValueError:
            closure.append({"type": "empty-cell"})
        else:
            closure.append(_state(value, explicit, set()))
    referenced_globals = []
    for name in sorted(_referenced_global_names(function.__code__)):
        if name == "__builtins__" or name not in function.__globals__:
            continue
        referenced_globals.append(
            {"name": name, "state": _state(function.__globals__[name], explicit, set())}
        )
    return {
        "kind": "function",
        "code": _code(function.__code__),
        "defaults": _state(function.__defaults__, explicit, set()),
        "kwdefaults": _state(function.__kwdefaults__, explicit, set()),
        "closure": closure,
        "referenced_globals": referenced_globals,
    }


def _instance_state(instance: Any, explicit: str | None) -> Any:
    values: dict[str, Any] = {}
    try:
        values.update(vars(instance))
    except TypeError:
        pass
    for base in type(instance).__mro__:
        slots = base.__dict__.get("__slots__", ())
        if type(slots) is str:
            slots = (slots,)
        for name in slots:
            if name in {"__dict__", "__weakref__"} or name in values:
                continue
            try:
                values[name] = getattr(instance, name)
            except AttributeError:
                continue
    values.pop("__execution_kernel_revision__", None)
    return _state(values, explicit, set())


def _class_state(handler_type: type, explicit: str | None) -> Any:
    """Bind class data and reject opaque class behavior conservatively."""

    values: dict[str, Any] = {}
    ignored = {
        "__classcell__",
        "__dict__",
        "__weakref__",
        "__module__",
        "__qualname__",
        "__execution_kernel_revision__",
    }
    for base in handler_type.__mro__:
        prefix = f"{base.__module__}.{base.__qualname__}"
        for name, value in base.__dict__.items():
            if name in ignored or name == "__call__":
                continue
            if name.startswith("__") and name.endswith("__"):
                continue
            key = f"{prefix}.{name}"
            if isinstance(value, (types.FunctionType, staticmethod, classmethod, property)):
                if explicit is None:
                    raise TypeError(
                        "handler class contains opaque behavior; set a non-empty "
                        "__execution_kernel_revision__ deployment revision"
                    )
                values[key] = _external_marker(value, explicit)
            else:
                values[key] = _state(value, explicit, set())
    return _state(values, explicit, set())


def _handler_manifest(handler: Handler) -> dict[str, Any]:
    explicit = _explicit_revision(handler)
    if isinstance(handler, types.FunctionType):
        implementation = _function_manifest(handler, explicit)
    elif isinstance(handler, types.MethodType):
        implementation = {
            "kind": "bound-method",
            "function": _function_manifest(handler.__func__, explicit),
            "instance_state": _instance_state(handler.__self__, explicit),
            "class_state": _class_state(type(handler.__self__), explicit),
        }
    else:
        call = getattr(type(handler), "__call__", None)
        if not isinstance(call, types.FunctionType):
            if explicit is None:
                raise TypeError(
                    "handler implementation is not fingerprintable; set "
                    "__execution_kernel_revision__"
                )
            implementation = {"kind": "opaque-callable"}
        else:
            implementation = {
                "kind": "callable-instance",
                "call": _function_manifest(call, explicit),
                "instance_state": _instance_state(handler, explicit),
                "class_state": _class_state(type(handler), explicit),
            }
    return {"implementation": implementation, "deployment_revision": explicit}


def registry_revision(handlers: Mapping[Any, Handler]) -> str:
    """Return a path-independent implementation and deployment fingerprint."""

    normalized = normalize_handlers(handlers)
    entries = []
    for (handler_id, version), handler in sorted(normalized.items()):
        entries.append(
            {
                "handler_id": handler_id,
                "contract_version": version,
                **_handler_manifest(handler),
            }
        )
    manifest = {"format": "execution-kernel-handler-registry-v2", "handlers": entries}
    return hashlib.sha256(_canonical_text(manifest).encode("utf-8")).hexdigest()


def handler_revision(
    handlers: Mapping[Any, Handler], handler_id: str, contract_version: int = 1
) -> str:
    """Bind one named handler's implementation, contract, and deployment state.

    Unrelated bindings do not contribute to this fingerprint. The prefix keeps
    this opt-in binding distinct from the existing complete-registry revision.
    """

    if type(handler_id) is not str or not handler_id.strip():
        raise TypeError("handler_id must be a non-empty string")
    if type(contract_version) is not int or contract_version < 1:
        raise TypeError("handler contract version must be a positive integer")
    normalized = normalize_handlers(handlers)
    key = (handler_id, contract_version)
    if key not in normalized:
        raise KeyError(f"unknown handler binding {key!r}")
    return "handler-v1:" + registry_revision({key: normalized[key]})
