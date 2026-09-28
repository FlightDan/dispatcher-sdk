from __future__ import annotations

import unittest

from dispatcher_sdk.orchestrator.managed_revision_preview import (
    ManagedRevisionPreviewError,
    preview_managed_revision,
)


def _task(task_id: str, *dependencies: str, payload: str | None = None) -> dict:
    task = {"task_id": task_id, "dependencies": list(dependencies)}
    if payload is not None:
        task["payload"] = payload
    return task


def _proof(task_id: str) -> dict:
    return {
        "result_id": f"result:{task_id}",
        "content_identity": f"sha256:{task_id}",
        "source_generation": 3,
        "compatible": True,
        "application_valid": True,
    }


class ManagedRevisionPreviewTests(unittest.TestCase):
    def test_wait_parent_and_its_consumers_join_dependency_invalidation_closure(self):
        graph = [_task("a"), _task("b", "a"), _task("c"), _task("d", "b")]
        preview = preview_managed_revision(
            graph, graph, changed_task_ids=["c"],
            wait_relations=[{
                "wait_id": "wait-b-c", "parent_task_id": "b",
                "waited_task_id": "c", "registered": True,
            }],
            artifact_relations=[],
            reuse_evidence={"a": _proof("a")},
        )

        self.assertEqual(preview["changed_task_ids"], ["c"])
        self.assertEqual(preview["impacted_task_ids"], ["b", "c", "d"])
        self.assertEqual(preview["must_recompute_task_ids"], ["b", "c", "d"])
        self.assertEqual([item["task_id"] for item in preview["reuse_candidates"]], ["a"])
        self.assertEqual(preview["blockers"], [])
        self.assertFalse(preview["commit_safe"])

    def test_artifact_consumers_extend_the_same_transitive_closure(self):
        graph = [_task("producer"), _task("consumer"), _task("last", "consumer")]
        preview = preview_managed_revision(
            graph, graph, changed_task_ids=["producer"],
            wait_relations=[],
            artifact_relations=[{
                "artifact_id": "artifact-1", "producer_task_id": "producer",
                "consumer_task_id": "consumer", "registered": True,
            }],
            reuse_evidence={},
        )

        self.assertEqual(preview["impacted_task_ids"], ["consumer", "last", "producer"])
        self.assertEqual(preview["must_recompute_task_ids"],
                         ["consumer", "last", "producer"])

    def test_missing_relation_inventories_block_reuse_and_force_full_rebuild(self):
        graph = [_task("a"), _task("b")]
        preview = preview_managed_revision(
            graph, graph, changed_task_ids=["a"],
            reuse_evidence={"b": _proof("b")},
        )

        self.assertFalse(preview["evidence_complete"])
        self.assertEqual(preview["impacted_task_ids"], ["a", "b"])
        self.assertEqual(preview["must_recompute_task_ids"], ["a", "b"])
        self.assertEqual(preview["reuse_candidates"], [])
        self.assertEqual({item["code"] for item in preview["blockers"]}, {
            "wait_evidence_missing", "artifact_evidence_missing",
        })

    def test_unknown_changed_id_blocks_and_forces_conservative_rebuild(self):
        graph = [_task("a"), _task("b")]
        preview = preview_managed_revision(
            graph, graph, changed_task_ids=["outside"],
            wait_relations=[], artifact_relations=[],
        )

        self.assertEqual(preview["impacted_task_ids"], ["a", "b"])
        self.assertFalse(preview["impact_complete"])
        self.assertIn("unknown_changed_task", {item["code"] for item in preview["blockers"]})

    def test_unregistered_wait_is_reported_and_included_in_closure(self):
        graph = [_task("parent"), _task("child")]
        preview = preview_managed_revision(
            graph, graph, changed_task_ids=["child"],
            wait_relations=[{
                "wait_id": "wait-1", "parent_task_id": "parent",
                "waited_task_id": "child", "registered": False,
            }],
            artifact_relations=[],
        )

        self.assertEqual(preview["impacted_task_ids"], ["child", "parent"])
        self.assertFalse(preview["evidence_complete"])
        self.assertIn("unregistered_wait", {item["code"] for item in preview["blockers"]})

    def test_deleted_dependency_and_cycle_are_blockers(self):
        deleted = preview_managed_revision(
            [_task("removed"), _task("consumer", "removed")],
            [_task("consumer", "removed")],
            changed_task_ids=[], wait_relations=[], artifact_relations=[],
        )
        self.assertIn("deleted_dependency", {item["code"] for item in deleted["blockers"]})
        self.assertIn("consumer", deleted["must_recompute_task_ids"])

        cyclic = preview_managed_revision(
            [_task("a"), _task("b"), _task("c")],
            [_task("a", "b"), _task("b", "a"), _task("c", "b")],
            changed_task_ids=[], wait_relations=[], artifact_relations=[],
        )
        cycles = [item for item in cyclic["blockers"] if item["code"] == "task_graph_cycle"]
        self.assertTrue(any(item.get("graph") == "new" and item["task_ids"] == ["a", "b"]
                            for item in cycles))
        self.assertEqual(cyclic["must_recompute_task_ids"], ["a", "b", "c"])

    def test_only_complete_claims_are_reported_as_candidates_and_never_safe(self):
        graph = [_task("unchanged")]
        preview = preview_managed_revision(
            graph, graph, changed_task_ids=[], wait_relations=[], artifact_relations=[],
            reuse_evidence={"unchanged": _proof("unchanged")},
        )

        self.assertEqual(preview["must_recompute_task_ids"], [])
        self.assertEqual([item["task_id"] for item in preview["reuse_candidates"]], ["unchanged"])
        self.assertFalse(preview["commit_safe"])
        self.assertEqual(preview["blockers"], [])

    def test_unproved_reuse_is_recomputed_with_missing_claim_fields(self):
        graph = [_task("changed"), _task("unchanged")]
        updated = [_task("changed", payload="v2"), _task("unchanged")]
        preview = preview_managed_revision(
            graph, updated, changed_task_ids=[], wait_relations=[], artifact_relations=[],
            reuse_evidence={"unchanged": {"result_id": "result:unchanged"}},
        )
        self.assertEqual(preview["changed_task_ids"], ["changed"])
        self.assertEqual(preview["must_recompute_task_ids"], ["changed", "unchanged"])
        self.assertEqual(preview["reuse_candidates"], [])
        self.assertEqual(preview["blockers"][0]["code"], "reuse_unproved")

    def test_output_digest_and_order_are_independent_of_input_order(self):
        first = preview_managed_revision(
            [_task("b", "a"), _task("a")], [_task("b", "a"), _task("a")],
            changed_task_ids=["a"], wait_relations=[], artifact_relations=[],
        )
        second = preview_managed_revision(
            [_task("a"), _task("b", "a")], [_task("a"), _task("b", "a")],
            changed_task_ids=["a"], wait_relations=[], artifact_relations=[],
        )
        self.assertEqual(first, second)

    def test_inputs_require_strict_json_and_nonempty_ids(self):
        with self.assertRaises(ManagedRevisionPreviewError):
            preview_managed_revision(
                [_task("a", payload=float("nan"))], [_task("a")],
                changed_task_ids=[], wait_relations=[], artifact_relations=[],
            )
        with self.assertRaises(ManagedRevisionPreviewError):
            preview_managed_revision(
                [_task("a", payload={1: "not-a-JSON-object-key"})], [_task("a")],
                changed_task_ids=[], wait_relations=[], artifact_relations=[],
            )
        with self.assertRaises(ManagedRevisionPreviewError):
            preview_managed_revision(
                [_task("a", payload=("tuple-is-not-JSON",))], [_task("a")],
                changed_task_ids=[], wait_relations=[], artifact_relations=[],
            )
        with self.assertRaises(ManagedRevisionPreviewError):
            preview_managed_revision(
                [_task("a")], [_task("a")], changed_task_ids=[" "],
                wait_relations=[], artifact_relations=[],
            )


if __name__ == "__main__":
    unittest.main()
