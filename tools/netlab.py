#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloudflare_api import CloudflareAPI, CloudflareAPIError  # noqa: E402
from migrations import apply_local_migrations, apply_remote_migrations  # noqa: E402
from project_config import ProjectConfig, load_project_config  # noqa: E402
from worker_bundle import build_worker_modules  # noqa: E402
from worker_vendor import vendor_worker_dependencies  # noqa: E402

DEFAULT_LOCAL_DB = ROOT / ".local" / "netlab-usage.sqlite3"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="netlab.py",
        description="Python-only development and deployment tools for netlab-usage-ingest.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    dev = sub.add_parser("dev", help="Run FastAPI locally with SQLite")
    dev.add_argument("--host", default="127.0.0.1")
    dev.add_argument("--port", type=int, default=8787)
    dev.add_argument("--reload", action=argparse.BooleanOptionalAction, default=True)
    dev.add_argument("--db", type=Path, default=DEFAULT_LOCAL_DB)

    vendor = sub.add_parser("vendor", help="Vendor Worker Python dependencies")
    vendor.add_argument("--clean", action=argparse.BooleanOptionalAction, default=True)

    deploy = sub.add_parser("deploy", help="Upload the Python Worker via Cloudflare REST API")
    deploy.add_argument("--no-vendor", action="store_true")
    deploy.add_argument("--dry-run", action="store_true")
    deploy.add_argument(
        "--workers-dev",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override the workers.dev setting from wrangler.jsonc",
    )

    report = sub.add_parser("report", help="Run the aggregate report against remote D1")
    report.add_argument("--file", type=Path, default=ROOT / "queries" / "summary.sql")

    query = sub.add_parser("query", help="Execute a SQL file against remote D1")
    query.add_argument("--file", type=Path, required=True)

    db = sub.add_parser("db", help="D1/SQLite database operations")
    db_sub = db.add_subparsers(dest="db_command", required=True)
    create = db_sub.add_parser("create", help="Create the remote D1 database")
    create.add_argument("--name")
    migrate = db_sub.add_parser("migrate", help="Apply SQL migrations")
    where = migrate.add_mutually_exclusive_group(required=True)
    where.add_argument("--local", action="store_true")
    where.add_argument("--remote", action="store_true")
    migrate.add_argument("--db", type=Path, default=DEFAULT_LOCAL_DB)

    return parser


def main(argv: list[str] | None = None) -> int:
    os.chdir(ROOT)
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_project_config(ROOT / "wrangler.jsonc")
        if args.command == "dev":
            return command_dev(args, config)
        if args.command == "vendor":
            return command_vendor(args)
        if args.command == "deploy":
            return command_deploy(args, config)
        if args.command == "report":
            return command_query(args.file, config)
        if args.command == "query":
            return command_query(args.file, config)
        if args.command == "db" and args.db_command == "create":
            return command_db_create(args, config)
        if args.command == "db" and args.db_command == "migrate":
            return command_db_migrate(args, config)
    except (CloudflareAPIError, RuntimeError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    parser.error("unknown command")
    return 2


def command_dev(args: argparse.Namespace, config: ProjectConfig) -> int:
    applied = apply_local_migrations(args.db, ROOT / config.migrations_dir)
    _print_migrations(applied, "local")
    env = os.environ.copy()
    env["NETLAB_LOCAL_DB"] = str(args.db)
    for name, value in config.vars.items():
        env.setdefault(name, value)
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "local_runtime:create_app",
        "--factory",
        "--app-dir",
        str(SRC),
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        command.append("--reload")
    print(f"Local SQLite: {args.db}")
    print(f"Endpoint: http://{args.host}:{args.port}/v1/submissions")
    return subprocess.call(command, env=env)


def command_vendor(args: argparse.Namespace) -> int:
    vendor_worker_dependencies(ROOT, clean=args.clean)
    return 0


def command_deploy(args: argparse.Namespace, config: ProjectConfig) -> int:
    database_id = _require_database_id(config)
    if not args.no_vendor:
        result = command_vendor(argparse.Namespace(clean=True))
        if result:
            return result

    modules = build_worker_modules(ROOT)
    metadata = _worker_metadata(config, database_id)
    total_bytes = sum(module.path.stat().st_size for module in modules)
    workers_dev = config.workers_dev if args.workers_dev is None else args.workers_dev
    if args.dry_run:
        print(json.dumps(metadata, indent=2, sort_keys=True))
        print(f"Bundle: {len(modules)} modules ({total_bytes:,} bytes)")
        print(f"workers.dev: {'enabled' if workers_dev else 'disabled'}")
        return 0

    account_id, api_token = _cloudflare_credentials()
    print(
        f"Uploading {len(modules)} modules ({total_bytes:,} bytes) "
        f"as Worker {config.worker_name!r}..."
    )
    with CloudflareAPI(account_id, api_token) as api:
        result = api.upload_worker(config.worker_name, metadata, modules)
        api.set_worker_subdomain(config.worker_name, enabled=workers_dev)
        if config.crons:
            api.set_cron_triggers(config.worker_name, config.crons)
    print(f"Deployed Worker: {result.get('id', config.worker_name)}")
    if config.crons:
        print("Cron triggers: " + ", ".join(config.crons))
    return 0


def command_db_create(args: argparse.Namespace, config: ProjectConfig) -> int:
    account_id, api_token = _cloudflare_credentials()
    name = args.name or config.d1_database_name
    with CloudflareAPI(account_id, api_token) as api:
        result = api.create_d1(name)
    database_id = result.get("uuid") or result.get("id")
    if not database_id:
        raise RuntimeError("Cloudflare created D1 but did not return a database UUID")
    print(f"Created D1 database {name!r}: {database_id}")
    print("Set this in your shell before migrate/deploy:")
    print(f"export CLOUDFLARE_D1_DATABASE_ID={database_id}")
    return 0


def command_db_migrate(args: argparse.Namespace, config: ProjectConfig) -> int:
    if args.local:
        applied = apply_local_migrations(args.db, ROOT / config.migrations_dir)
        _print_migrations(applied, "local")
        print(f"Local SQLite: {args.db}")
        return 0

    database_id = _require_database_id(config)
    account_id, api_token = _cloudflare_credentials()
    with CloudflareAPI(account_id, api_token) as api:
        applied = apply_remote_migrations(api, database_id, ROOT / config.migrations_dir)
    _print_migrations(applied, "remote D1")
    return 0


def command_query(path: Path, config: ProjectConfig) -> int:
    database_id = _require_database_id(config)
    if not path.is_file():
        raise RuntimeError(f"SQL file not found: {path}")
    account_id, api_token = _cloudflare_credentials()
    with CloudflareAPI(account_id, api_token) as api:
        result = api.query_d1(database_id, path.read_text(encoding="utf-8"))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _worker_metadata(config: ProjectConfig, database_id: str) -> dict[str, Any]:
    bindings: list[dict[str, Any]] = [
        {
            "type": "d1",
            "name": config.d1_binding,
            "database_id": database_id,
        }
    ]
    bindings.extend(
        {"type": "plain_text", "name": name, "text": value}
        for name, value in config.vars.items()
    )
    if (
        config.ratelimit_binding
        and config.ratelimit_namespace_id
        and config.ratelimit_limit is not None
        and config.ratelimit_period is not None
    ):
        bindings.append(
            {
                "type": "ratelimit",
                "name": config.ratelimit_binding,
                "namespace_id": config.ratelimit_namespace_id,
                "simple": {
                    "limit": config.ratelimit_limit,
                    "period": config.ratelimit_period,
                },
            }
        )

    return {
        "main_module": Path(config.main).name,
        "compatibility_date": config.compatibility_date,
        "compatibility_flags": list(config.compatibility_flags),
        "bindings": bindings,
        "observability": {"enabled": config.observability_enabled},
    }


def _cloudflare_credentials() -> tuple[str, str]:
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    missing = [
        name
        for name, value in (
            ("CLOUDFLARE_ACCOUNT_ID", account_id),
            ("CLOUDFLARE_API_TOKEN", api_token),
        )
        if not value
    ]
    if missing:
        raise RuntimeError("missing environment variable(s): " + ", ".join(missing))
    return account_id, api_token


def _require_database_id(config: ProjectConfig) -> str:
    if not config.d1_database_id:
        raise RuntimeError(
            "D1 database ID is not configured. Set CLOUDFLARE_D1_DATABASE_ID "
            "or replace the placeholder database_id in wrangler.jsonc."
        )
    return config.d1_database_id


def _print_migrations(applied: list[str], target: str) -> None:
    if applied:
        for name in applied:
            print(f"Applied {name} to {target}")
    else:
        print(f"No pending migrations for {target}")


if __name__ == "__main__":
    raise SystemExit(main())
