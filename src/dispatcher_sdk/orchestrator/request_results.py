"""Request correlation and explicit caller receipts over the existing inbox.

This is an adapter-facing journal, not a transport or proof of comprehension.
Use a dedicated NotificationInbox: its messages are immutable facts here and
must not be claimed by a generic notification worker. No new schema is needed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .contracts import CommandConflict, clone, digest, identifier
from .inbox import NotificationInbox


@dataclass(frozen=True)
class RequestResultIdentity:
    source_id: str
    caller_id: str
    request_id: str
    execution_id: str
    result_id: str
    result_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RequestResultObservation:
    identity: RequestResultIdentity
    result: Any
    recorded_at: float
    delivery_reported_at: float | None
    received_confirmed_at: float | None
    # Monotonic, independent facts: a caller receipt may race a transport receipt.
    snapshot_scope: str = "independent_inbox_reads"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _keys(source_id: str, caller_id: str, request_id: str) -> tuple[str, str]:
    for value, name in ((source_id, "source_id"), (caller_id, "caller_id"),
                        (request_id, "request_id")):
        identifier(value, name)
    return ("request-results-v1:" + digest([source_id, caller_id]), digest(request_id))


class RequestResultInbox:
    """Keep one immutable result per source/caller/request and separate receipts.

    The application persists request identities before submission and maps each
    fan-out result to a distinct request. Caller IDs are stable namespaces, not
    authentication: an adapter must authenticate the actual caller before it
    accepts ``confirm_received``. Recording or reading a result never confirms
    reception. Missing receipts mean *unconfirmed*, not proof of non-delivery.
    """

    def __init__(self, inbox: NotificationInbox):
        if not isinstance(inbox, NotificationInbox):
            raise TypeError("inbox must be a NotificationInbox")
        self.inbox = inbox

    def record_result(self, source_id: str, caller_id: str, request_id: str, *,
                      execution_id: str, result_id: str, result: Any) -> RequestResultIdentity:
        """Commit a supplied terminal result before acknowledging its producer.

        Producer completion is asserted by the adapter; this method does not
        run a task or certify a business outcome. Identical retries are safe,
        including after receipts have been recorded; different content conflicts.
        """
        source, key = _keys(source_id, caller_id, request_id)
        identifier(execution_id, "execution_id")
        identifier(result_id, "result_id")
        value = clone(result)
        identity = RequestResultIdentity(source_id, caller_id, request_id,
                                         execution_id, result_id, digest(value))
        self.inbox.accept(source, {
            "kind": "request_result_v1", "generation": 0,
            "identity": identity.to_dict(), "result": value,
        }, notification_id="result:" + key)
        return identity

    def _result(self, source_id: str, caller_id: str, request_id: str):
        source, key = _keys(source_id, caller_id, request_id)
        row = self.inbox.get(source, "result:" + key)
        payload = row["payload"]
        if type(payload) is not dict or payload.get("kind") != "request_result_v1":
            raise CommandConflict("request result journal contains an invalid record")
        try:
            identity = RequestResultIdentity(**payload["identity"])
            valid = ((identity.source_id, identity.caller_id, identity.request_id)
                     == (source_id, caller_id, request_id)
                     and identity.result_digest == digest(payload["result"]))
        except (KeyError, TypeError, ValueError) as error:
            raise CommandConflict("request result journal contains invalid identity/content") from error
        if not valid:
            raise CommandConflict("request result identity/content does not match its key")
        return row, identity

    def _receipt_time(self, source: str, key: str, kind: str,
                      identity: RequestResultIdentity) -> float | None:
        try:
            row = self.inbox.get(source, kind + ":" + key)
        except KeyError:
            return None
        expected = {"kind": kind, "generation": 0, "identity": identity.to_dict()}
        if row["payload"] != expected:
            raise CommandConflict("request result receipt does not match the result")
        return row["created_at"]

    def lookup(self, source_id: str, caller_id: str,
               request_id: str) -> RequestResultObservation | None:
        """Point-read a late result and receipts without acknowledging anything.

        None means this journal has no result for this scope, not that execution
        failed or does not exist. Receipts are independent snapshots and may be
        added concurrently; retry the query to observe later acknowledgements.
        """
        source, key = _keys(source_id, caller_id, request_id)
        try:
            row, identity = self._result(source_id, caller_id, request_id)
        except KeyError:
            return None
        return RequestResultObservation(
            identity, row["payload"]["result"], row["created_at"],
            self._receipt_time(source, key, "delivered", identity),
            self._receipt_time(source, key, "received", identity),
        )

    def _record_receipt(self, identity: RequestResultIdentity, kind: str) -> None:
        if not isinstance(identity, RequestResultIdentity):
            raise TypeError("identity must be a RequestResultIdentity")
        source, key = _keys(identity.source_id, identity.caller_id, identity.request_id)
        _, actual = self._result(identity.source_id, identity.caller_id, identity.request_id)
        if actual != identity:
            raise CommandConflict("receipt identity differs from the persisted result")
        # Publications are immutable. Validation and this append need no shared
        # transaction: a later publisher cannot replace the validated identity.
        self.inbox.accept(source, {
            "kind": kind, "generation": 0, "identity": identity.to_dict(),
        }, notification_id=kind + ":" + key)

    def mark_delivered(self, identity: RequestResultIdentity) -> None:
        """Record the transport's report; it is not caller confirmation."""
        self._record_receipt(identity, "delivered")

    def confirm_received(self, identity: RequestResultIdentity) -> None:
        """Persist an explicit, authenticated-by-adapter caller acknowledgement.

        Do not call this merely because a tool returned or its producer finished.
        A receipt asserts reception of this canonical result content, not comprehension,
        successful review, or authorization of any subsequent business action.
        """
        self._record_receipt(identity, "received")


__all__ = ["RequestResultInbox", "RequestResultIdentity", "RequestResultObservation"]
