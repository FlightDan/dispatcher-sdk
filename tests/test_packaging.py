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
        self.assertRegex(metadata, r'(?m)^version = "0\.6\.0"$')
        self.assertRegex(metadata, r'(?m)^dependencies = \[\]$')
        source_version = (SOURCE / "_version.py").read_text(encoding="utf-8")
        self.assertRegex(source_version, r'(?m)^SOURCE_VERSION = "0\.6\.0"$')

    def test_core_is_dependency_free_and_provider_imports_are_lazy(self):
        sources = list(SOURCE.rglob("*.py"))
        self.assertGreater(len(sources), 20, "boundary check must inspect actual SDK sources")
        for source in sources:
            tree = ast.parse(source.read_text(encoding="utf-8"))
            lazy_provider_nodes = set()
            if source == SOURCE / "adapters" / "opensandbox.py":
                sdk_loader = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_sdk")
                lazy_provider_nodes = set(ast.walk(sdk_loader))
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
                    if module.split(".")[0] == "opensandbox":
                        self.assertIn(node, lazy_provider_nodes, "provider SDK imports must stay inside the optional loader")
                        continue
                    self.assertIn(module.split(".")[0], sys.stdlib_module_names | {"dispatcher_sdk"},
                                  f"external dependency in {source.relative_to(ROOT)}:{node.lineno}: {module}")

    def test_kernel_does_not_import_orchestrator(self):
        for source in (SOURCE / "execution_kernel").rglob("*.py"):
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                    if node.level > 1 and not (node.level == 2 and node.module == "durability"):
                        self.fail(f"Kernel reaches outside its package: {source}:{node.lineno}")
                else:
                    continue
                for module in modules:
                    self.assertNotIn("orchestrator", module.split("."),
                                     f"Kernel imports orchestrator: {source}:{node.lineno}")


if __name__ == "__main__":
    unittest.main()
