import json
import sqlite3
import unittest

from dispatcher_sdk.content import (
    CONTENT_PREFIX,
    CONTENT_SCHEMA,
    ContentIntegrityError,
    ContentReadBudget,
    ContentSizeLimitError,
    MAX_DEPTH,
    decode_value,
    encode_value,
    _object_digest,
)
from dispatcher_sdk.orchestrator.contracts import canonical


class ContentCodecTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.addCleanup(self.connection.close)
        self.connection.executescript(CONTENT_SCHEMA)

    def object_count(self):
        return self.connection.execute(
            "SELECT count(*) FROM sdk_content_objects"
        ).fetchone()[0]

    def test_read_budget_is_shared_between_root_decodes(self):
        budget = ContentReadBudget(2)
        self.assertEqual(decode_value(self.connection, "1", read_budget=budget), 1)
        self.assertEqual(decode_value(self.connection, "2", read_budget=budget), 2)
        with self.assertRaises(ContentSizeLimitError):
            decode_value(self.connection, "3", read_budget=budget)

    def test_read_budget_rejects_an_object_before_fetching_its_body(self):
        encoded = encode_value(self.connection, {"value": "x" * 100}, threshold=1)
        statements = []
        self.connection.set_trace_callback(statements.append)
        with self.assertRaises(ContentSizeLimitError):
            decode_value(self.connection, encoded,
                         read_budget=ContentReadBudget(len(encoded.encode("utf-8"))))
        self.assertFalse(any(statement.startswith("SELECT encoded FROM sdk_content_objects")
                             for statement in statements))

    def test_round_trip_is_deterministic_and_uses_canonical_json_semantics(self):
        value = {
            "unicode": "雪とé",
            "values": [None, False, True, -3, 1.25, {"z": 1, "a": "first"}],
        }
        first = encode_value(self.connection, value, threshold=10_000)
        second = encode_value(self.connection, value, threshold=10_000)
        self.assertTrue(first.startswith(CONTENT_PREFIX))
        self.assertEqual(first, second)
        decoded = decode_value(self.connection, first)
        self.assertEqual(decoded, json.loads(canonical(value)))
        self.assertEqual(canonical(decoded), canonical(value))

    def test_stable_large_child_is_reused_when_a_sibling_changes(self):
        stable = "high-entropy-ish:" + "".join(chr(33 + index % 80) for index in range(300))
        first = encode_value(self.connection, {"blob": stable, "counter": "A"}, threshold=64)
        count_after_a = self.object_count()
        second = encode_value(self.connection, {"blob": stable, "counter": "B"}, threshold=64)
        count_after_b = self.object_count()
        third = encode_value(self.connection, {"blob": stable, "counter": "A"}, threshold=64)
        self.assertEqual(count_after_a, 2)
        self.assertEqual(count_after_b, 3)
        self.assertEqual(self.object_count(), 3)
        self.assertNotEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(decode_value(self.connection, second)["blob"], stable)

    def test_typed_nodes_cannot_collide_with_user_reference_markers(self):
        value = {
            "ref": "0" * 64,
            "logical_bytes": 123,
            "nested": {"tag": "ref", "digest": "1" * 64},
            "list": ["ref", "2" * 64, 4],
        }
        encoded = encode_value(self.connection, value, threshold=20)
        self.assertEqual(decode_value(self.connection, encoded), value)

    def test_plain_json_is_a_legacy_fallback(self):
        encoded = canonical({"unencoded": ["legacy", 1], "雪": True})
        self.assertEqual(decode_value(self.connection, encoded), json.loads(encoded))
        self.assertEqual(self.object_count(), 0)

    def test_missing_object_is_an_integrity_error(self):
        encoded = encode_value(self.connection, "large value" * 20, threshold=16)
        self.connection.execute("DELETE FROM sdk_content_objects")
        with self.assertRaisesRegex(ContentIntegrityError, "missing"):
            decode_value(self.connection, encoded)

    def test_digest_and_length_metadata_are_verified(self):
        encoded = encode_value(self.connection, "large value" * 20, threshold=16)
        digest = self.connection.execute(
            "SELECT digest FROM sdk_content_objects"
        ).fetchone()[0]
        original = self.connection.execute(
            "SELECT encoded, logical_bytes FROM sdk_content_objects WHERE digest=?",
            (digest,),
        ).fetchone()

        self.connection.execute(
            "UPDATE sdk_content_objects SET encoded=? WHERE digest=?",
            (canonical(["string", "different large value"]), digest),
        )
        with self.assertRaisesRegex(ContentIntegrityError, "digest"):
            decode_value(self.connection, encoded)

        self.connection.execute(
            "UPDATE sdk_content_objects SET encoded=?, logical_bytes=? WHERE digest=?",
            (original[0], original[1] + 1, digest),
        )
        with self.assertRaisesRegex(ContentIntegrityError, "length"):
            decode_value(self.connection, encoded)

    def test_depth_and_logical_size_limits_apply_to_encode_and_decode(self):
        value = "payload" * 20
        encoded = encode_value(self.connection, value, threshold=16)
        with self.assertRaisesRegex(ContentIntegrityError, "maximum"):
            decode_value(self.connection, encoded, max_logical_bytes=32)
        with self.assertRaisesRegex(ValueError, "maximum"):
            encode_value(
                self.connection,
                value,
                threshold=16,
                max_logical_bytes=32,
            )

        nested = 0
        for _ in range(8):
            nested = [nested]
        deep_encoded = encode_value(
            self.connection, nested, threshold=10_000, max_depth=10
        )
        with self.assertRaisesRegex(ContentIntegrityError, "depth"):
            decode_value(self.connection, deep_encoded, max_depth=4)
        with self.assertRaisesRegex(ValueError, "depth"):
            encode_value(self.connection, nested, threshold=10_000, max_depth=4)

    def test_bad_typed_reference_is_rejected_without_marker_confusion(self):
        malformed = CONTENT_PREFIX + canonical(["ref", "not-a-digest", 1])
        with self.assertRaisesRegex(ContentIntegrityError, "reference"):
            decode_value(self.connection, malformed)

    def test_noncyclic_reference_chain_has_a_depth_limit(self):
        logical_bytes = len(canonical("end").encode("utf-8"))
        object_encoded = canonical(["string", "end"])
        digest = _object_digest(object_encoded)
        self.connection.execute(
            "INSERT INTO sdk_content_objects VALUES(?,?,?)",
            (digest, object_encoded, logical_bytes),
        )
        for _ in range(5):
            object_encoded = canonical(["ref", digest, logical_bytes])
            digest = _object_digest(object_encoded)
            self.connection.execute(
                "INSERT INTO sdk_content_objects VALUES(?,?,?)",
                (digest, object_encoded, logical_bytes),
            )
        root = CONTENT_PREFIX + canonical(["ref", digest, logical_bytes])
        with self.assertRaisesRegex(ContentIntegrityError, "reference chain"):
            decode_value(self.connection, root, max_depth=2)

    def test_oversized_stored_body_is_rejected_before_body_selection(self):
        digest = "a" * 64
        self.connection.execute(
            "INSERT INTO sdk_content_objects VALUES(?,?,?)",
            (digest, " " * 5000, 1),
        )
        root = CONTENT_PREFIX + canonical(["ref", digest, 1])
        statements = []
        self.connection.set_trace_callback(statements.append)
        try:
            with self.assertRaisesRegex(ContentIntegrityError, "encoded size"):
                decode_value(
                    self.connection,
                    root,
                    max_logical_bytes=1,
                    max_encoded_bytes=10_000,
                )
        finally:
            self.connection.set_trace_callback(None)
        self.assertTrue(any("length(CAST(encoded AS BLOB))" in sql for sql in statements))
        self.assertFalse(any("SELECT encoded FROM sdk_content_objects" in sql for sql in statements))

    def test_oversized_malformed_root_is_rejected_before_json_parsing(self):
        malformed = CONTENT_PREFIX + ("[" + " " * 1000)
        with self.assertRaisesRegex(ContentIntegrityError, "encoded size"):
            decode_value(
                self.connection,
                malformed,
                max_logical_bytes=100,
                max_encoded_bytes=100,
            )

    def test_threshold_one_reference_tree_round_trips_with_wire_budget(self):
        value = list(range(100))
        encoded = encode_value(
            self.connection,
            value,
            threshold=1,
            max_logical_bytes=1000,
            max_encoded_bytes=20_000,
        )
        self.assertEqual(
            decode_value(
                self.connection,
                encoded,
                max_logical_bytes=1000,
                max_encoded_bytes=20_000,
            ),
            value,
        )

    def test_depth_limit_round_trips_with_exact_reference_budget(self):
        value = None
        for _ in range(MAX_DEPTH):
            value = [value]

        encoded = encode_value(self.connection, value, threshold=1)

        self.assertEqual(self.object_count(), MAX_DEPTH)
        self.assertEqual(decode_value(self.connection, encoded), value)

    def test_object_writes_are_owned_by_the_callers_transaction(self):
        self.connection.commit()
        encode_value(self.connection, {"blob": "x" * 200}, threshold=16)
        self.assertTrue(self.connection.in_transaction)
        self.assertGreater(self.object_count(), 0)
        self.connection.rollback()
        self.assertEqual(self.object_count(), 0)

    def test_cycles_are_rejected_before_any_object_is_inserted(self):
        value = []
        value.append(value)
        with self.assertRaisesRegex(ValueError, "acyclic"):
            encode_value(self.connection, value, threshold=16)
        self.assertEqual(self.object_count(), 0)


if __name__ == "__main__":
    unittest.main()
