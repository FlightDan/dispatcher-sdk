"""Check links and run README Python blocks against text outputs in document order.

A platform marker immediately before a Python fence limits that example only.
"""
from pathlib import Path
import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import unquote


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.append(str(root))
    from tests._acceptance_evidence import retained_directory
    documents = list(root.glob("*.md")) + list((root / "docs").glob("*.md"))
    documents += list((root / "src").rglob("README.md"))
    for directory in ("wiki", "DocsforAgents"):
        documents += list((root / directory).glob("*.md"))
    failures = []
    links = 0
    for document in documents:
        content = document.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
            target = unquote(target.split("#", 1)[0])
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            links += 1
            if not (document.parent / target).exists():
                failures.append(f"{document.relative_to(root)}: missing {target}")
    if failures:
        raise SystemExit("\n".join(failures))
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    executed = 0
    skipped = 0
    for name in ("README.md", "README.zh-CN.md"):
        content = (root / name).read_text(encoding="utf-8")
        if "—" in content or "–" in content:
            raise SystemExit(f"{name}: remove editorial dash punctuation")
        blocks = re.findall(
            r"(?:<!-- example-platform: (\w+) -->\s*)?```python\n(.*?)\n```",
            content, re.DOTALL,
        )
        if not blocks:
            raise SystemExit(f"{name}: missing runnable example")
        outputs = re.findall(r"```text\n(.*?)\n```", content, re.DOTALL)
        if len(outputs) != len(blocks):
            raise SystemExit(f"{name}: each Python example needs a text output block")
        platforms = {"": True, "posix": hasattr(os, "fork"),
                     "linux": sys.platform.startswith("linux") and hasattr(os, "fork")}
        for index, ((platform, code), output) in enumerate(zip(blocks, outputs), 1):
            if platform not in platforms:
                raise SystemExit(f"{name}: unknown example platform {platform}")
            if not platforms[platform]:
                print(f"Skipped {name} example {index}: requires {platform}")
                skipped += 1
                continue
            directory = retained_directory(f"sdk-docs-{name}-example-{index}-")
            example = directory / "readme_example.py"
            (directory / "readme_snippet.py").write_text(code, encoding="utf-8")
            # Keep handlers in __main__; Windows imports this script as
            # __mp_main__, so only the original parent installs diagnostics.
            prelude = ("if __name__ == '__main__':\n"
                       "    import sys as _evidence_sys\n"
                       f"    _evidence_sys.path.append({str(root)!r})\n"
                       "    from tests._readme_evidence import install as _install_evidence\n"
                       f"    _install_evidence({str(directory)!r})\n\n")
            example.write_text(prelude + code, encoding="utf-8")
            evidence = {"document": name, "example": index, "platform": platform,
                        "interpreter": sys.executable, "script": str(example),
                        "subprocess_timeout_seconds": 30, "began": time.monotonic()}
            stdout = stderr = ""
            try:
                result = subprocess.run([sys.executable, str(example)], cwd=directory,
                                        env=environment, capture_output=True, text=True, timeout=30)
                evidence["returncode"] = result.returncode
                stdout, stderr = result.stdout, result.stderr
            except subprocess.TimeoutExpired as error:
                evidence["error"] = {"type": type(error).__name__, "message": str(error)}
                stdout, stderr = error.stdout or "", error.stderr or ""
                raise
            finally:
                evidence["returned"] = time.monotonic()
                # TimeoutExpired may expose bytes even with text=True.
                try:
                    for filename, value in (("stdout.txt", stdout), ("stderr.txt", stderr)):
                        (directory / filename).write_text(
                            value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value,
                            encoding="utf-8")
                    (directory / "checker.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                except Exception as error:
                    print(f"README checker evidence capture failed: {error}", file=sys.stderr)
            if result.returncode or result.stdout.strip() != output.strip():
                raise SystemExit(f"{name} example {index} failed: {result.stdout}\n{result.stderr}")
            executed += 1
    print(f"Checked {links} local links; {executed} README examples passed, {skipped} skipped")


if __name__ == "__main__":
    main()
