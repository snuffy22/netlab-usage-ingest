from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Cloudflare's current Python Workers toolchain targets CPython 3.13 on
# Pyodide 0.28.x.  PyEmscripten is the standardized PEP 783 platform tag;
# Pyodide's package index still contains some wheels using the legacy tag.
TARGET_PYTHON = "3.13"
TARGET_IMPLEMENTATION = "cp"
TARGET_ABIS = ("cp313", "abi3", "none")
TARGET_PLATFORMS = (
    "pyemscripten_2025_0_wasm32",
    "pyodide_2025_0_wasm32",
    "emscripten_4_0_9_wasm32",
)
PYODIDE_INDEX = "https://index.pyodide.org/0.28.3"


def vendor_worker_dependencies(
    root: str | Path = ".",
    *,
    clean: bool = False,
    python: str | Path | None = None,
) -> None:
    project_root = Path(root).resolve()
    requirements = project_root / "requirements-worker.txt"
    target = project_root / "python_modules"

    if not requirements.is_file():
        raise RuntimeError(f"Worker requirements file not found: {requirements}")

    if clean and target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    interpreter = str(python or sys.executable)
    command = [
        interpreter,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--target",
        str(target),
        "--only-binary=:all:",
        "--no-compile",
        "--python-version",
        TARGET_PYTHON,
        "--implementation",
        TARGET_IMPLEMENTATION,
    ]
    for abi in TARGET_ABIS:
        command.extend(("--abi", abi))
    for platform in TARGET_PLATFORMS:
        command.extend(("--platform", platform))
    command.extend(
        (
            "--extra-index-url",
            PYODIDE_INDEX,
            "--requirement",
            str(requirements),
        )
    )

    print("Vendoring Cloudflare/Pyodide Worker dependencies with pip...")
    print(f"Target: Python {TARGET_PYTHON}, {TARGET_PLATFORMS[0]}")
    completed = subprocess.run(command, cwd=project_root, check=False)
    if completed.returncode:
        raise RuntimeError(
            "pip could not resolve a complete PyEmscripten/Pyodide wheel set. "
            "Make sure the virtualenv uses an up-to-date pip and that every Worker "
            "dependency publishes a pure-Python or compatible WebAssembly wheel."
        )

    _remove_host_only_artifacts(target)
    marker = target / ".vendored"
    marker.write_text(
        f"python={TARGET_PYTHON}\nplatform={TARGET_PLATFORMS[0]}\n",
        encoding="utf-8",
    )


def build_pip_vendor_command(
    root: str | Path = ".", *, python: str | Path | None = None
) -> list[str]:
    """Return the target-platform pip command, primarily for diagnostics/tests."""
    project_root = Path(root).resolve()
    requirements = project_root / "requirements-worker.txt"
    target = project_root / "python_modules"
    interpreter = str(python or sys.executable)
    command = [
        interpreter,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--target",
        str(target),
        "--only-binary=:all:",
        "--no-compile",
        "--python-version",
        TARGET_PYTHON,
        "--implementation",
        TARGET_IMPLEMENTATION,
    ]
    for abi in TARGET_ABIS:
        command.extend(("--abi", abi))
    for platform in TARGET_PLATFORMS:
        command.extend(("--platform", platform))
    command.extend(
        (
            "--extra-index-url",
            PYODIDE_INDEX,
            "--requirement",
            str(requirements),
        )
    )
    return command


def _remove_host_only_artifacts(target: Path) -> None:
    # pip may create script entry points for dependencies. Worker imports need package
    # modules/data only; host shell scripts are neither useful nor portable in Pyodide.
    scripts = target / "bin"
    if scripts.is_dir():
        shutil.rmtree(scripts)

    for path in target.rglob("*.pyc"):
        path.unlink(missing_ok=True)
    for path in sorted(target.rglob("__pycache__"), reverse=True):
        if path.is_dir():
            shutil.rmtree(path)
