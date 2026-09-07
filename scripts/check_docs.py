"""Check links and run README Python blocks against text outputs in document order.

A platform marker immediately before a Python fence limits that example only.
"""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
from urllib.parse import unquote


def main():
    root = Path(__file__).resolve().parents[1]
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
            with tempfile.TemporaryDirectory() as directory:
                example = Path(directory) / "readme_example.py"
                example.write_text(code, encoding="utf-8")
                result = subprocess.run([sys.executable, str(example)], cwd=directory,
                                        env=environment, capture_output=True, text=True, timeout=30)
                if result.returncode or result.stdout.strip() != output.strip():
                    raise SystemExit(f"{name} example {index} failed: {result.stdout}\n{result.stderr}")
                executed += 1
    print(f"Checked {links} local links; {executed} README examples passed, {skipped} skipped")


if __name__ == "__main__":
    main()
