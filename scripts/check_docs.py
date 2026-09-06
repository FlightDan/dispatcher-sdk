"""Check local Markdown links and execute the README's complete Python example."""
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
    for name in ("README.md", "README.zh-CN.md"):
        content = (root / name).read_text(encoding="utf-8")
        if "—" in content or "–" in content:
            raise SystemExit(f"{name}: remove editorial dash punctuation")
        blocks = re.findall(r"```python\n(.*?)\n```", content, re.DOTALL)
        if not blocks:
            raise SystemExit(f"{name}: missing runnable example")
        for code in blocks:
            with tempfile.TemporaryDirectory() as directory:
                result = subprocess.run([sys.executable, "-c", code], cwd=directory,
                                        env=environment, capture_output=True, text=True, timeout=30)
                if result.returncode or result.stdout.strip() != "{'total': 60}":
                    raise SystemExit(f"{name} example failed: {result.stdout}\n{result.stderr}")
    print(f"Checked {links} local links and both README examples")


if __name__ == "__main__":
    main()
