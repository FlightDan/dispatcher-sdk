"""A late result is durable even when its original caller has disconnected."""

from pathlib import Path
from tempfile import TemporaryDirectory

from dispatcher_sdk.orchestrator import NotificationInbox, RequestResultInbox


def main():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "request-results.db"
        journal = RequestResultInbox(NotificationInbox(path))

        # In an adapter, persist these source/caller/request IDs before submission.
        # Record the terminal result before ACKing its upstream result delivery.
        identity = journal.record_result(
            "production-01", "review-session-17", "tool-request-4",
            execution_id="execution-42", result_id="result-42",
            result={"status": "succeeded", "output": "build log available"},
        )
        journal.mark_delivered(identity)  # Transport reported a send, not reception.

        # Reconnect after the caller/adapter restarted. Querying does not ACK.
        reopened = RequestResultInbox(NotificationInbox(path))
        late = reopened.lookup("production-01", "review-session-17", "tool-request-4")
        assert late is not None and late.received_confirmed_at is None
        print("result recorded; transport reported delivery; caller unconfirmed")

        # Only a separate explicit caller ACK reaches this code. The adapter must
        # authenticate the caller and bind it to late.identity.caller_id first.
        reopened.confirm_received(late.identity)
        assert reopened.lookup("production-01", "review-session-17", "tool-request-4").received_confirmed_at is not None
        print("caller confirmed reception; business verdict remains application-owned")


if __name__ == "__main__":
    main()
