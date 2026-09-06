"""Strict globally ordered execution-event contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .contracts import (
    JSONValue,
    SCHEMA_VERSION,
    _StrictContract,
    _finite,
    _identifier,
    _integer,
    _json_copy,
    _optional_identifier,
    _schema_version,
)


@dataclass(frozen=True, slots=True)
class Event(_StrictContract):
    """One immutable execution event in the global Kernel sequence."""

    sequence: int
    event_id: str
    execution_id: str
    revision: int
    event_type: str
    from_state: Optional[str]
    to_state: str
    data: JSONValue
    created_at: float
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _integer(self.sequence, "sequence", minimum=1)
        _identifier(self.event_id, "event_id")
        _identifier(self.execution_id, "execution_id")
        _integer(self.revision, "revision", minimum=1)
        _identifier(self.event_type, "event_type")
        _optional_identifier(self.from_state, "from_state")
        _identifier(self.to_state, "to_state")
        data = _json_copy(self.data, "data")
        created = _finite(self.created_at, "created_at")
        _schema_version(self.schema_version, type(self).__name__)
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "created_at", created)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "execution_id": self.execution_id,
            "revision": self.revision,
            "event_type": self.event_type,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "data": _json_copy(self.data, "data"),
            "created_at": self.created_at,
            "schema_version": self.schema_version,
        }
