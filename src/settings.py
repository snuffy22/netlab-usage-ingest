from __future__ import annotations

from typing import Any

DEFAULT_MAX_BODY_BYTES = 65_536
DEFAULT_RETENTION_DAYS = 30


def integer_setting(
    env: Any,
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(getattr(env, name))
    except (AttributeError, TypeError, ValueError):
        return default
    return value if minimum <= value <= maximum else default
