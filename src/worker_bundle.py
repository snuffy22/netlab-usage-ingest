from __future__ import annotations

import mimetypes
from pathlib import Path

from cloudflare_api import WorkerModule

_SOURCE_FILES = (
    "entry.py",
    "app.py",
    "models.py",
    "normalize.py",
    "allowlists.py",
    "storage.py",
    "settings.py",
)


def build_worker_modules(root: str | Path = ".") -> list[WorkerModule]:
    project_root = Path(root)
    modules: list[WorkerModule] = []

    src = project_root / "src"
    for filename in _SOURCE_FILES:
        path = src / filename
        if not path.is_file():
            raise RuntimeError(f"required Worker source file is missing: {path}")
        modules.append(WorkerModule(filename, path, "text/x-python"))

    vendor_root = project_root / "python_modules"
    if not vendor_root.is_dir():
        raise RuntimeError(
            "python_modules/ does not exist; run `python tools/netlab.py vendor` first"
        )

    for path in sorted(vendor_root.rglob("*")):
        if not path.is_file() or _excluded(path):
            continue
        relative = path.relative_to(project_root).as_posix()
        modules.append(WorkerModule(relative, path, content_type(path)))

    return modules


def content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "text/x-python"
    if suffix in {".txt", ".pth", ".cfg", ".ini", ".json", ".toml", ".md"}:
        return "text/plain"
    if suffix == ".wasm":
        return "application/wasm"
    if suffix == ".map":
        return "application/source-map"
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed and guessed.startswith("text/"):
        return "text/plain"
    return "application/octet-stream"


def _excluded(path: Path) -> bool:
    return (
        path.name in {".synced", ".vendored"}
        or path.suffix == ".pyc"
        or "__pycache__" in path.parts
    )
