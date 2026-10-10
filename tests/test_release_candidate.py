from __future__ import annotations

import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_candidate.py"
SPEC = importlib.util.spec_from_file_location("release_candidate", SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
COMMIT = "a" * 40
VERSION = "0.7.2"


def run_record(run_id=100, attempt=1):
    return {"id": run_id, "workflow_id": 10, "path": release.WORKFLOW_PATH,
            "repository": {"full_name": "owner/repo"},
            "head_repository": {"full_name": "owner/repo"}, "head_sha": COMMIT,
            "event": "push", "status": "completed", "conclusion": "success",
            "run_attempt": attempt}


class FakeGitHub:
    repository = "owner/repo"

    def __init__(self):
        self.runs = [run_record()]
        self.jobs = [{"name": name, "status": "completed", "conclusion": "success"}
                     for name in sorted(release.EXPECTED_JOBS)]
        self.artifacts = [{"id": 500, "name": "release-packages-100-1", "expired": False,
                           "workflow_run": {"id": 100, "head_sha": COMMIT}}]
        self.calls = []
        self.download = b""
        self.refreshed = None

    def request(self, endpoint):
        self.calls.append(endpoint)
        if endpoint == "actions/workflows/ci.yml":
            return {"id": 10, "path": release.WORKFLOW_PATH}
        if endpoint.startswith("actions/runs/"):
            return copy.deepcopy(self.refreshed or next(run for run in self.runs if str(run["id"]) == endpoint.split("/")[-1]))
        raise AssertionError(endpoint)

    def items(self, endpoint, key):
        self.calls.append(endpoint)
        return copy.deepcopy({"workflow_runs": self.runs, "jobs": self.jobs,
                              "artifacts": self.artifacts}[key])

    def archive(self, artifact_id):
        self.calls.append(artifact_id)
        return self.download


def zip_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return stream.getvalue()


def packages(*, wheel_version=VERSION, sdist_version=VERSION, source_version=VERSION,
             project_version=VERSION, sdist_link=False):
    wheel = zip_bytes([
        (f"dispatcher_sdk-{VERSION}.dist-info/METADATA",
         f"Name: dispatcher-sdk\nVersion: {wheel_version}\n"),
        ("dispatcher_sdk/_version.py", f'SOURCE_VERSION = "{source_version}"\n'),
        (f"dispatcher_sdk-{VERSION}.dist-info/licenses/LICENSE", "license text"),
        (f"dispatcher_sdk-{VERSION}.dist-info/licenses/NOTICE", "notice text"),
    ])
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, data in [
            ("PKG-INFO", f"Name: dispatcher-sdk\nVersion: {sdist_version}\n"),
            ("src/dispatcher_sdk/_version.py", f'SOURCE_VERSION = "{source_version}"\n'),
            ("pyproject.toml", f'[project]\nname = "dispatcher-sdk"\nversion = "{project_version}"\n\n[tool.setuptools]\n'),
            ("LICENSE", "license text"), ("NOTICE", "notice text"),
        ]:
            data = data.encode()
            member = tarfile.TarInfo(f"dispatcher_sdk-{VERSION}/{name}")
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        if sdist_link:
            member = tarfile.TarInfo(f"dispatcher_sdk-{VERSION}/escape")
            member.type = tarfile.SYMTYPE
            member.linkname = "/tmp/outside"
            archive.addfile(member)
    return [(f"dispatcher_sdk-{VERSION}-py3-none-any.whl", wheel),
            (f"dispatcher_sdk-{VERSION}.tar.gz", stream.getvalue())]


class ReleaseCandidateTests(unittest.TestCase):
    def test_reuses_full_same_commit_acceptance_and_original_artifact(self):
        api = FakeGitHub()
        self.assertEqual(release.find_candidate(api, COMMIT, required=True), {
            "run_id": 100, "run_attempt": 1, "artifact_id": 500,
            "artifact_name": "release-packages-100-1"})
        self.assertIn("actions/runs/100/attempts/1/jobs?per_page=100", api.calls)
        self.assertEqual(len(release.EXPECTED_JOBS), 17)

    def test_reused_run_with_skipped_matrix_cannot_prove_acceptance(self):
        api = FakeGitHub()
        for job in api.jobs:
            job["conclusion"] = "skipped"
        self.assertEqual(release.find_candidate(api, COMMIT), {})
        with self.assertRaisesRegex(release.CandidateError, "did not all succeed"):
            release.find_candidate(api, COMMIT, required=True)

    def test_missing_duplicate_and_failed_matrix_jobs_do_not_qualify(self):
        for alteration in ("missing", "duplicate", "failed"):
            with self.subTest(alteration=alteration):
                api = FakeGitHub()
                if alteration == "missing":
                    api.jobs.pop()
                elif alteration == "duplicate":
                    api.jobs.append(copy.deepcopy(api.jobs[0]))
                else:
                    api.jobs[0]["conclusion"] = "failure"
                self.assertEqual(release.find_candidate(api, COMMIT), {})

    def test_partial_rerun_cannot_reuse_previous_attempt_artifact(self):
        api = FakeGitHub()
        api.runs[0]["run_attempt"] = 2
        self.assertEqual(release.find_candidate(api, COMMIT), {})
        self.assertIn("actions/runs/100/attempts/2/jobs?per_page=100", api.calls)
        api.artifacts[0]["name"] = "release-packages-100-2"
        api.jobs = api.jobs[:1]
        self.assertEqual(release.find_candidate(api, COMMIT), {})

    def test_expired_missing_and_duplicate_artifacts_do_not_qualify(self):
        for alteration in ("expired", "missing", "duplicate"):
            with self.subTest(alteration=alteration):
                api = FakeGitHub()
                if alteration == "expired":
                    api.artifacts[0]["expired"] = True
                elif alteration == "missing":
                    api.artifacts.clear()
                else:
                    api.artifacts.append(copy.deepcopy(api.artifacts[0]))
                self.assertEqual(release.find_candidate(api, COMMIT), {})

    def test_current_run_and_untrusted_events_are_excluded(self):
        api = FakeGitHub()
        self.assertEqual(release.find_candidate(api, COMMIT, exclude_run=100), {})
        for event in ("pull_request", "workflow_call"):
            api.runs[0]["event"] = event
            self.assertEqual(release.find_candidate(api, COMMIT), {})
        api.runs[0]["event"] = "workflow_dispatch"
        self.assertEqual(release.find_candidate(api, COMMIT)["run_id"], 100)

    def test_run_and_artifact_identity_mismatch_is_an_error(self):
        mutations = (
            lambda api: api.runs[0].update(head_sha="b" * 40),
            lambda api: api.runs[0].update(workflow_id=11),
            lambda api: api.runs[0].update(repository={"full_name": "other/repo"}),
            lambda api: api.artifacts[0]["workflow_run"].update(id=99),
            lambda api: api.artifacts[0]["workflow_run"].update(head_sha="b" * 40),
        )
        for mutate in mutations:
            api = FakeGitHub()
            mutate(api)
            with self.assertRaises(release.CandidateError):
                release.find_candidate(api, COMMIT)

    def test_malformed_api_records_fail_instead_of_requesting_another_matrix(self):
        mutations = (
            lambda api: api.runs[0].pop("run_attempt"),
            lambda api: api.runs[0].pop("conclusion"),
            lambda api: api.runs[0].pop("event"),
            lambda api: api.jobs[0].pop("name"),
            lambda api: api.jobs[0].pop("conclusion"),
            lambda api: api.artifacts[0].pop("expired"),
        )
        for mutate in mutations:
            api = FakeGitHub()
            mutate(api)
            with self.assertRaises(release.CandidateError):
                release.find_candidate(api, COMMIT)

    def test_new_rerun_during_lookup_prevents_reuse(self):
        api = FakeGitHub()
        api.refreshed = run_record(attempt=2)
        api.refreshed.update(status="in_progress", conclusion=None)
        self.assertEqual(release.find_candidate(api, COMMIT), {})

    def test_newer_skipped_run_does_not_hide_original_full_run(self):
        api = FakeGitHub()
        api.runs.append(run_record(101))
        api.runs[-1].update(status="completed", conclusion="cancelled")
        self.assertEqual(release.find_candidate(api, COMMIT)["run_id"], 100)

    def test_api_pagination_collects_every_page(self):
        api = release.GitHub("owner/repo")
        response = [{"jobs": [{"name": "first"}]}, {"jobs": [{"name": "last"}]}]
        completed = subprocess.CompletedProcess([], 0,
            stdout=("\n".join(json.dumps(page) for page in response) + "\n").encode())
        with patch.object(release.subprocess, "run", return_value=completed) as call:
            self.assertEqual(api.items("actions/runs/100/jobs?per_page=100", "jobs"),
                             [{"name": "first"}, {"name": "last"}])
        self.assertIn("--paginate", call.call_args.args[0])
        self.assertNotIn("--slurp", call.call_args.args[0])

    def test_api_failure_and_malformed_json_remain_errors(self):
        api = release.GitHub("owner/repo")
        failure = subprocess.CalledProcessError(4, ["gh", "api"])
        with patch.object(release.subprocess, "run", side_effect=failure):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                api.request("actions/workflows/ci.yml")
            self.assertIs(raised.exception, failure)
        malformed = subprocess.CompletedProcess([], 0, stdout=b"not JSON")
        with patch.object(release.subprocess, "run", return_value=malformed):
            with self.assertRaisesRegex(release.CandidateError, "invalid API JSON"):
                api.request("actions/workflows/ci.yml")
        for malformed_pages in ([], {}, [{"not_jobs": []}], [{"jobs": ["invalid"]}]):
            with patch.object(api, "request", return_value=malformed_pages):
                with self.assertRaises(release.CandidateError):
                    api.items("jobs", "jobs")
        with patch.object(api, "request", return_value=[{"total_count": 2, "jobs": [{"name": "only"}]}]):
            with self.assertRaisesRegex(release.CandidateError, "incomplete"):
                api.items("jobs", "jobs")
        incomplete = subprocess.CompletedProcess([], 0,
            stdout=b'{"total_count":2,"jobs":[]}\n{"jobs":')
        with patch.object(release.subprocess, "run", return_value=incomplete):
            with self.assertRaisesRegex(release.CandidateError, "invalid API JSON"):
                api.items("jobs", "jobs")

    def test_download_preserves_original_wheel_and_sdist_bytes(self):
        api = FakeGitHub()
        originals = packages()
        api.download = zip_bytes(originals)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "dist"
            result = release.download_packages(api, 500, destination, VERSION)
            self.assertEqual(len(result["packages"]), 2)
            self.assertEqual(api.calls, [500])
            for name, data in originals:
                self.assertEqual((destination / name).read_bytes(), data)

    def test_download_rejects_extra_unsafe_duplicate_and_missing_members(self):
        for alteration in ("extra", "unsafe", "missing", "duplicate", "invalid"):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as temporary:
                api = FakeGitHub()
                entries = packages()
                if alteration == "extra":
                    entries.append(("unexpected.txt", b"extra"))
                elif alteration == "unsafe":
                    entries[0] = ("../outside.whl", entries[0][1])
                elif alteration == "missing":
                    entries.pop()
                elif alteration == "duplicate":
                    entries = [entries[0], entries[0]]
                with patch("warnings.warn"):
                    api.download = b"invalid zip" if alteration == "invalid" else zip_bytes(entries)
                destination = Path(temporary) / "dist"
                with self.assertRaises(release.CandidateError):
                    release.download_packages(api, 500, destination, VERSION)
                self.assertFalse(destination.exists())

    def test_download_rejects_wrong_package_versions_and_unsafe_sdist(self):
        for options in ({"wheel_version": "0.7.0"}, {"sdist_version": "0.7.0"},
                        {"source_version": "0.7.0"}, {"project_version": "0.7.0"},
                        {"sdist_link": True}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as temporary:
                api = FakeGitHub()
                api.download = zip_bytes(packages(**options))
                destination = Path(temporary) / "dist"
                with self.assertRaises(release.CandidateError):
                    release.download_packages(api, 500, destination, VERSION)
                self.assertFalse(destination.exists())

    def test_download_never_overwrites_existing_files(self):
        api = FakeGitHub()
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            existing = destination / "keep.txt"
            existing.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(release.CandidateError, "absent or empty"):
                release.download_packages(api, 500, destination, VERSION)
            self.assertEqual(existing.read_text(encoding="utf-8"), "keep")
            self.assertEqual(api.calls, [])


if __name__ == "__main__":
    unittest.main()
