import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _venv_python(tmp_path: Path) -> Path:
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def test_core_install_imports_scripted_adapter_without_google_genai(tmp_path: Path):
    python = _venv_python(tmp_path)
    subprocess.run(["uv", "pip", "install", "--python", str(python), str(ROOT)], check=True)
    code = """
import importlib.util
from agy_swarms.adapters.scripted import ScriptedAdapter

print(ScriptedAdapter.accounting)
try:
    spec = importlib.util.find_spec("google.genai")
except ModuleNotFoundError:
    spec = None
print(spec)
"""

    result = subprocess.run(
        [
            str(python),
            "-c",
            code,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["exact", "None"]


def test_gemini_extra_installs_gemini_adapter_dependency(tmp_path: Path):
    python = _venv_python(tmp_path)
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), f"{ROOT}[gemini]"],
        check=True,
    )

    result = subprocess.run(
        [
            str(python),
            "-c",
            "from agy_swarms.adapters.gemini_api import GeminiApiAdapter; print(GeminiApiAdapter.accounting)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "exact"
