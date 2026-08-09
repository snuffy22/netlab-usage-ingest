from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from app import app
from local_d1 import LocalD1

DEFAULT_LOCAL_DB = Path(".local/netlab-usage.sqlite3")


def create_app():
    db_path = Path(os.getenv("NETLAB_LOCAL_DB", str(DEFAULT_LOCAL_DB)))
    env = SimpleNamespace(
        DB=LocalD1(db_path),
        BATCH_RETENTION_DAYS=os.getenv("BATCH_RETENTION_DAYS", "30"),
        MAX_BODY_BYTES=os.getenv("MAX_BODY_BYTES", "65536"),
    )
    app.state.env = env
    return app
