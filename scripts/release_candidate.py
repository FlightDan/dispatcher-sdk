#!/usr/bin/env python3
"""Reuse complete CI acceptance and its original distribution files for release."""
from __future__ import annotations

import argparse
import ast
import email
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import zipfile


WORKFLOW_PATH = ".github/workflows/ci.yml"
EXPECTED_JOBS = frozenset(
    f"{runner} / Python {version} / {architecture}"
    for runner, architecture in (
        ("ubuntu-latest", "x64"), ("ubuntu-24.04-arm", "arm64"),
        ("windows-latest", "x64"), ("windows-11-arm", "arm64"),
    )
    for version in ("3.10", "3.11", "3.12", "3.13")
    if not (runner == "windows-11-arm" and version == "3.10")
) | {"windows-11-arm / Python 3.10 / x64", "secrets"}


class CandidateError(Exception):
    """Release provenance or package input is missing or malformed."""


def require_mapping(value, context):
    if not isinstance(value, dict):
        raise CandidateError(f"{context}: expected an object")
    return value


def positive_id(value, context):
    if type(value) is not int or value <= 0:
        raise CandidateError(f"{context}: expected a positive integer")
    return value


def text_field(record, key, context):
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise CandidateError(f"{context}: missing {key}")
    return value


class GitHub:
    def __init__(self, repository):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise CandidateError("repository must be OWNER/REPO")
        self.repository = repository

    def request(self, endpoint, *, paginated=False):
        command = ["gh", "api", f"repos/{self.repository}/{endpoint}"]
        if paginated:
            command.append("--paginate")
        # Leave stderr untouched so authentication, permission and API failures
        # retain the original gh diagnostic instead of becoming 'no candidate'.
        completed = subprocess.run(command, stdout=subprocess.PIPE, check=True)
        try:
            if not paginated:
                return json.loads(completed.stdout)
            # Older gh versions support --paginate without --slurp. Decode
            # each complete page object, retaining malformed/truncated input
            # as a visible error rather than treating it as an empty result.
            source = completed.stdout.decode("utf-8")
            decoder = json.JSONDecoder()
            pages, offset = [], 0
            while source[offset:].strip():
                offset += len(source[offset:]) - len(source[offset:].lstrip())
                page, offset = decoder.raw_decode(source, offset)
                pages.append(page)
            return pages
        except (ValueError, UnicodeError) as exc:
            raise CandidateError(f"{endpoint}: invalid API JSON: {exc}") from exc

    def items(self, endpoint, key):
        pages = self.request(endpoint, paginated=True)
        if not isinstance(pages, list) or not pages:
            raise CandidateError(f"{endpoint}: missing paginated response")
        records = []
        totals = []
        for page in pages:
            page = require_mapping(page, endpoint)
            if "total_count" in page:
                total = page["total_count"]
                if type(total) is not int or total < 0:
                    raise CandidateError(f"{endpoint}: invalid total_count")
                totals.append(total)
            values = page.get(key)
            if not isinstance(values, list):
                raise CandidateError(f"{endpoint}: missing {key} array")
            records.extend(require_mapping(value, f"{endpoint}/{key}") for value in values)
        if totals and (len(set(totals)) != 1 or totals[0] != len(records)):
            raise CandidateError(f"{endpoint}: incomplete or changing paginated response")
        return records

    def archive(self, artifact_id):
        return subprocess.run(
            ["gh", "api", f"repos/{self.repository}/actions/artifacts/{artifact_id}/zip"],
            stdout=subprocess.PIPE, check=True,
        ).stdout


def find_candidate(api, commit, *, exclude_run=None, required=False):
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise CandidateError("commit must be a complete Git commit ID")
    workflow = require_mapping(api.request("actions/workflows/ci.yml"), "CI workflow")
    workflow_id = positive_id(workflow.get("id"), "CI workflow id")
    if workflow.get("path") != WORKFLOW_PATH:
        raise CandidateError("CI workflow path does not match ci.yml")
    runs = api.items(f"actions/workflows/{workflow_id}/runs?head_sha={commit}&per_page=100", "workflow_runs")
    for run in runs:
        positive_id(run.get("id"), "CI run id")
    reasons = []
    for run in sorted(runs, key=lambda value: value["id"], reverse=True):
        run_id = run["id"]
        if run_id == exclude_run:
            continue
        repository = require_mapping(run.get("repository"), f"run {run_id} repository")
        head_repository = require_mapping(run.get("head_repository"), f"run {run_id} head repository")
        if text_field(repository, "full_name", f"run {run_id} repository").lower() != api.repository.lower():
            raise CandidateError(f"run {run_id}: repository mismatch")
        if run.get("workflow_id") != workflow_id or run.get("path") != WORKFLOW_PATH:
            raise CandidateError(f"run {run_id}: workflow identity mismatch")
        if text_field(run, "head_sha", f"run {run_id}").lower() != commit.lower():
            raise CandidateError(f"run {run_id}: commit mismatch in filtered API response")
        event = text_field(run, "event", f"run {run_id}")
        status = text_field(run, "status", f"run {run_id}")
        if "conclusion" not in run:
            raise CandidateError(f"run {run_id}: missing conclusion")
        attempt = positive_id(run.get("run_attempt"), f"run {run_id} attempt")
        if text_field(head_repository, "full_name", f"run {run_id} head repository").lower() != api.repository.lower():
            reasons.append(f"run {run_id}: external head repository")
            continue
        if event not in {"push", "workflow_dispatch"}:
            reasons.append(f"run {run_id}: untrusted event {run.get('event')!r}")
            continue
        if status != "completed" or run.get("conclusion") != "success":
            reasons.append(f"run {run_id}: {run.get('status')}/{run.get('conclusion')}")
            continue
        jobs = api.items(f"actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100", "jobs")
        for job in jobs:
            text_field(job, "name", f"run {run_id} job")
            text_field(job, "status", f"run {run_id} job")
            if "conclusion" not in job:
                raise CandidateError(f"run {run_id}: job missing conclusion")
        expected = [job for job in jobs if job.get("name") in EXPECTED_JOBS]
        names = [job["name"] for job in expected]
        if len(names) != len(EXPECTED_JOBS) or set(names) != EXPECTED_JOBS:
            reasons.append(f"run {run_id} attempt {attempt}: incomplete or duplicate acceptance jobs")
            continue
        if any(job.get("status") != "completed" or job.get("conclusion") != "success" for job in expected):
            reasons.append(f"run {run_id} attempt {attempt}: acceptance jobs did not all succeed")
            continue
        artifact_name = f"release-packages-{run_id}-{attempt}"
        artifacts = api.items(f"actions/runs/{run_id}/artifacts?per_page=100", "artifacts")
        for artifact in artifacts:
            text_field(artifact, "name", f"run {run_id} artifact")
        matches = [artifact for artifact in artifacts if artifact.get("name") == artifact_name]
        if len(matches) != 1:
            reasons.append(f"run {run_id} attempt {attempt}: expected one {artifact_name} artifact")
            continue
        artifact = matches[0]
        artifact_id = positive_id(artifact.get("id"), f"run {run_id} artifact id")
        if type(artifact.get("expired")) is not bool:
            raise CandidateError(f"artifact {artifact_id}: missing expired flag")
        if artifact["expired"]:
            reasons.append(f"artifact {artifact_id}: expired")
            continue
        provenance = require_mapping(artifact.get("workflow_run"), f"artifact {artifact_id} workflow run")
        if provenance.get("id") != run_id or text_field(provenance, "head_sha", f"artifact {artifact_id}").lower() != commit.lower():
            raise CandidateError(f"artifact {artifact_id}: workflow run provenance mismatch")
        latest = require_mapping(api.request(f"actions/runs/{run_id}"), f"run {run_id} refresh")
        positive_id(latest.get("run_attempt"), f"run {run_id} refreshed attempt")
        text_field(latest, "status", f"run {run_id} refresh")
        if "conclusion" not in latest:
            raise CandidateError(f"run {run_id}: refresh missing conclusion")
        if latest.get("id") != run_id or latest.get("head_sha") != run["head_sha"]:
            raise CandidateError(f"run {run_id}: identity changed during eligibility check")
        if (latest.get("run_attempt") != attempt or latest.get("status") != "completed"
                or latest.get("conclusion") != "success"):
            reasons.append(f"run {run_id}: rerun started during eligibility check")
            continue
        return {"run_id": run_id, "run_attempt": attempt,
                "artifact_id": artifact_id, "artifact_name": artifact_name}
    if required:
        raise CandidateError("No complete CI acceptance with retained packages for " + commit +
                             (": " + "; ".join(reasons) if reasons else ": no eligible runs"))
    return {}


def safe_member(name):
    path = PurePosixPath(name)
    if not name or "\\" in name or path.is_absolute() or ".." in path.parts:
        raise CandidateError(f"Unsafe archive member: {name!r}")


def check_metadata(data, version, context):
    metadata = email.message_from_bytes(data)
    if metadata.get_all("Name") != ["dispatcher-sdk"] or metadata.get_all("Version") != [version]:
        raise CandidateError(f"{context}: distribution name/version mismatch")


def check_source_version(data, version, context):
    try:
        tree = ast.parse(data.decode("utf-8"))
        assignments = [node.value.value for node in tree.body
                       if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "SOURCE_VERSION" for target in node.targets)
                       and isinstance(node.value, ast.Constant)]
    except (UnicodeError, SyntaxError) as exc:
        raise CandidateError(f"{context}: invalid runtime version source") from exc
    if assignments != [version]:
        raise CandidateError(f"{context}: runtime version mismatch")


def check_wheel(data, version):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise CandidateError("wheel: duplicate archive members")
        for name in names:
            safe_member(name)
        metadata_path = f"dispatcher_sdk-{version}.dist-info/METADATA"
        if [name for name in names if name.endswith(".dist-info/METADATA")] != [metadata_path]:
            raise CandidateError("wheel: missing or extra distribution metadata")
        check_metadata(archive.read(metadata_path), version, "wheel")
        check_source_version(archive.read("dispatcher_sdk/_version.py"), version, "wheel")
        for document in ("LICENSE", "NOTICE"):
            matches = [name for name in names if ".dist-info/" in name and name.endswith("/" + document)]
            if len(matches) != 1 or not archive.read(matches[0]).strip():
                raise CandidateError(f"wheel: missing or empty {document}")


def check_sdist(data, version):
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise CandidateError("sdist: duplicate archive members")
        prefix = f"dispatcher_sdk-{version}/"
        for member in members:
            safe_member(member.name)
            if not (member.name == prefix[:-1] or member.name.startswith(prefix)) or not (member.isfile() or member.isdir()):
                raise CandidateError(f"sdist: unexpected member {member.name!r}")
        def read(relative):
            member = archive.getmember(prefix + relative)
            if not member.isfile():
                raise CandidateError(f"sdist: {relative} is not a file")
            stream = archive.extractfile(member)
            if stream is None:
                raise CandidateError(f"sdist: cannot read {relative}")
            return stream.read()
        check_metadata(read("PKG-INFO"), version, "sdist")
        check_source_version(read("src/dispatcher_sdk/_version.py"), version, "sdist")
        text = read("pyproject.toml").decode("utf-8")
        project = re.search(r"(?ms)^\[project\]\s*\n(.*?)(?=^\[|\Z)", text)
        versions = re.findall(r'^version\s*=\s*[\"\']([^\"\']+)[\"\']\s*$', project[1], re.MULTILINE) if project else []
        if versions != [version]:
            raise CandidateError("sdist: pyproject version mismatch")
        for document in ("LICENSE", "NOTICE"):
            if not read(document).strip():
                raise CandidateError(f"sdist: empty {document}")


def download_packages(api, artifact_id, destination, version):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise CandidateError("version must be a formal X.Y.Z release")
    positive_id(artifact_id, "artifact id")
    destination = Path(destination)
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise CandidateError("package destination must be absent or empty")
    expected = {f"dispatcher_sdk-{version}-py3-none-any.whl", f"dispatcher_sdk-{version}.tar.gz"}
    try:
        with zipfile.ZipFile(io.BytesIO(api.archive(artifact_id))) as archive:
            names = archive.namelist()
            for name in names:
                safe_member(name)
            if len(names) != 2 or set(names) != expected:
                raise CandidateError("release artifact must contain exactly the expected wheel and sdist")
            packages = {name: archive.read(name) for name in names}
        check_wheel(packages[f"dispatcher_sdk-{version}-py3-none-any.whl"], version)
        check_sdist(packages[f"dispatcher_sdk-{version}.tar.gz"], version)
    except (zipfile.BadZipFile, tarfile.TarError, KeyError, UnicodeError, ValueError, EOFError) as exc:
        raise CandidateError(f"Invalid release package archive: {exc}") from exc
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in packages.items():
        (destination / name).write_bytes(data)
    return {"packages": [str(destination / name) for name in sorted(packages)]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    find = commands.add_parser("find")
    find.add_argument("--repository", required=True)
    find.add_argument("--commit", required=True)
    find.add_argument("--exclude-run", type=int)
    find.add_argument("--require", action="store_true")
    download = commands.add_parser("download")
    download.add_argument("--repository", required=True)
    download.add_argument("--artifact-id", required=True, type=int)
    download.add_argument("--destination", required=True)
    download.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    try:
        api = GitHub(args.repository)
        if args.command == "find":
            result = find_candidate(api, args.commit, exclude_run=args.exclude_run, required=args.require)
        else:
            result = download_packages(api, args.artifact_id, args.destination, args.version)
    except CandidateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
