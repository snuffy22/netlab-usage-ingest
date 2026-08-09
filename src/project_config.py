from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PLACEHOLDER_DATABASE_ID = "REPLACE_WITH_D1_DATABASE_ID"


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    worker_name: str
    main: str
    compatibility_date: str
    compatibility_flags: tuple[str, ...]
    vars: dict[str, str]
    d1_binding: str
    d1_database_name: str
    d1_database_id: str | None
    migrations_dir: str
    ratelimit_binding: str | None
    ratelimit_namespace_id: str | None
    ratelimit_limit: int | None
    ratelimit_period: int | None
    crons: tuple[str, ...]
    workers_dev: bool
    observability_enabled: bool


def load_project_config(path: str | Path = "wrangler.jsonc") -> ProjectConfig:
    config_path = Path(path)
    raw: dict[str, Any] = json.loads(_strip_jsonc_comments(config_path.read_text(encoding="utf-8")))

    d1 = _only(raw.get("d1_databases", []), "d1_databases")
    ratelimits = raw.get("ratelimits", [])
    ratelimit = _only(ratelimits, "ratelimits") if ratelimits else None
    simple = ratelimit.get("simple", {}) if ratelimit else {}

    configured_id = str(d1.get("database_id", "")).strip()
    database_id = os.getenv("CLOUDFLARE_D1_DATABASE_ID", "").strip()
    if not database_id and configured_id and configured_id != PLACEHOLDER_DATABASE_ID:
        database_id = configured_id

    return ProjectConfig(
        worker_name=str(raw["name"]),
        main=str(raw["main"]),
        compatibility_date=str(raw["compatibility_date"]),
        compatibility_flags=tuple(str(v) for v in raw.get("compatibility_flags", [])),
        vars={str(k): str(v) for k, v in raw.get("vars", {}).items()},
        d1_binding=str(d1["binding"]),
        d1_database_name=str(d1["database_name"]),
        d1_database_id=database_id or None,
        migrations_dir=str(d1.get("migrations_dir", "migrations")),
        ratelimit_binding=str(ratelimit["name"]) if ratelimit else None,
        ratelimit_namespace_id=str(ratelimit["namespace_id"]) if ratelimit else None,
        ratelimit_limit=int(simple["limit"]) if "limit" in simple else None,
        ratelimit_period=int(simple["period"]) if "period" in simple else None,
        crons=tuple(str(v) for v in raw.get("triggers", {}).get("crons", [])),
        workers_dev=bool(raw.get("workers_dev", True)),
        observability_enabled=bool(raw.get("observability", {}).get("enabled", False)),
    )


def _only(values: list[dict[str, Any]], label: str) -> dict[str, Any]:
    if len(values) != 1:
        raise ValueError(f"expected exactly one {label} entry, found {len(values)}")
    return values[0]


def _strip_jsonc_comments(text: str) -> str:
    """Remove // and /* */ comments while preserving comment markers in strings."""
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue

        if char == "/" and next_char == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue

        if char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(text) and text[index : index + 2] != "*/":
                index += 1
            index += 2
            continue

        output.append(char)
        index += 1

    return "".join(output)
