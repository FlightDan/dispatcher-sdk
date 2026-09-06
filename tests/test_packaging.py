from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest



ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "dispatcher_sdk"


class PackagingTests(unittest.TestCase):
    def test_project_metadata_names_dependency_free_sdk(self):
        metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertRegex(metadata, r'(?m)^name = "dispatcher-sdk"$')
        self.assertRegex(metadata, r'(?m)^version = "0\.5\.1"$')
        self.assertRegex(metadata, r'(?m)^dependencies = \[\]$')

    def test_entire_sdk_has_only_standard_library_and_sdk_imports(self):
        sources = list(SOURCE.rglob("*.py"))
        self.assertGreater(len(sources), 20, "boundary check must inspect actual SDK sources")
        for source in sources:
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    modules = [node.module or ""]
                elif isinstance(node, ast.Call) and (
                    isinstance(node.func, ast.Name) and node.func.id == "__import__"
                    or isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"
                ):
                    modules = [node.args[0].value] if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) else []
                else:
                    continue
                for module in modules:
                    self.assertIn(module.split(".")[0], sys.stdlib_module_names | {"dispatcher_sdk"},
                                  f"external dependency in {source.relative_to(ROOT)}:{node.lineno}: {module}")

    def test_kernel_does_not_import_orchestrator(self):
        for source in (SOURCE / "execution_kernel").rglob("*.py"):
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                    if node.level > 1:
                        self.fail(f"Kernel reaches outside its package: {source}:{node.lineno}")
                else:
                    continue
                for module in modules:
                    self.assertNotIn("orchestrator", module.split("."),
                                     f"Kernel imports orchestrator: {source}:{node.lineno}")


if __name__ == "__main__":
    unittest.main()
