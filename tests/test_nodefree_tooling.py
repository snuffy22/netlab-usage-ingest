from __future__ import annotations

from pathlib import Path

from project_config import load_project_config
from worker_bundle import build_worker_modules, content_type


def test_jsonc_config_parses_comments_and_url_strings(tmp_path, monkeypatch):
    config = tmp_path / "wrangler.jsonc"
    config.write_text(
        r'''{
          // a line comment
          "name": "test-worker",
          "main": "src/entry.py",
          "compatibility_date": "2026-08-06",
          "compatibility_flags": ["python_workers"],
          "workers_dev": false,
          "observability": {"enabled": true},
          "vars": {"EXAMPLE": "https://example.invalid/a//b"},
          "d1_databases": [{
            "binding": "DB",
            "database_name": "db",
            "database_id": "REPLACE_WITH_D1_DATABASE_ID",
            "migrations_dir": "migrations"
          }],
          /* a block comment */
          "ratelimits": [{
            "name": "LIMITER",
            "namespace_id": "1001",
            "simple": {"limit": 10, "period": 60}
          }],
          "triggers": {"crons": ["17 3 * * *"]}
        }''',
        encoding="utf-8",
    )
    monkeypatch.setenv("CLOUDFLARE_D1_DATABASE_ID", "remote-id")

    parsed = load_project_config(config)

    assert parsed.worker_name == "test-worker"
    assert parsed.d1_database_id == "remote-id"
    assert parsed.vars["EXAMPLE"] == "https://example.invalid/a//b"
    assert parsed.workers_dev is False
    assert parsed.observability_enabled is True


def test_worker_bundle_contains_sources_and_vendor_without_sync_token(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    for name in (
        "entry.py",
        "app.py",
        "models.py",
        "normalize.py",
        "allowlists.py",
        "storage.py",
        "settings.py",
    ):
        (src / name).write_text("# test\n", encoding="utf-8")

    vendor = tmp_path / "python_modules" / "package"
    vendor.mkdir(parents=True)
    (vendor / "__init__.py").write_text("", encoding="utf-8")
    (vendor / "extension.so").write_bytes(b"test")
    (tmp_path / "python_modules" / ".synced").write_text("version", encoding="utf-8")

    modules = build_worker_modules(tmp_path)
    by_name = {module.name: module for module in modules}

    assert "entry.py" in by_name
    assert by_name["entry.py"].content_type == "text/x-python"
    assert "python_modules/package/__init__.py" in by_name
    assert "python_modules/package/extension.so" in by_name
    assert "python_modules/.synced" not in by_name
    assert content_type(Path("extension.so")) == "application/octet-stream"


def test_vendor_command_targets_pyemscripten_without_uv_or_node(tmp_path):
    from worker_vendor import build_pip_vendor_command

    (tmp_path / "requirements-worker.txt").write_text("fastapi\n", encoding="utf-8")
    command = build_pip_vendor_command(tmp_path, python="/project/.venv/bin/python")
    joined = " ".join(command)

    assert command[:4] == ["/project/.venv/bin/python", "-m", "pip", "install"]
    assert "pyemscripten_2025_0_wasm32" in command
    assert "pyodide_2025_0_wasm32" in command
    assert "https://index.pyodide.org/0.28.3" in command
    assert "--only-binary=:all:" in command
    assert "uv" not in joined
    assert "node" not in joined
    assert "npx" not in joined
    assert "pywrangler" not in joined
