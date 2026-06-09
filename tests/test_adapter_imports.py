import subprocess
import sys
import tomllib
from pathlib import Path


def test_scripted_adapter_import_does_not_require_google_genai():
    code = """
import importlib.abc
import sys

class BlockGoogle(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "google" or fullname.startswith("google."):
            raise ModuleNotFoundError("blocked google import")
        return None

sys.meta_path.insert(0, BlockGoogle())
from agy_swarms.adapters.scripted import ScriptedAdapter
print(ScriptedAdapter.accounting)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "exact"


def test_google_genai_is_declared_as_gemini_extra_not_core_dependency():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    core_dependencies = pyproject["project"].get("dependencies", [])
    optional_dependencies = pyproject["project"]["optional-dependencies"]

    assert not any(dep.startswith("google-genai") for dep in core_dependencies)
    assert any(dep.startswith("google-genai") for dep in optional_dependencies["gemini"])
