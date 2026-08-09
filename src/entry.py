from __future__ import annotations

import asgi
from workers import WorkerEntrypoint

from app import app
from settings import DEFAULT_RETENTION_DAYS, integer_setting
from storage import prune_accepted_batches


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return await asgi.fetch(app, request, self.env)

    async def scheduled(self, _controller, env, _ctx):
        retention_days = integer_setting(
            env, 'BATCH_RETENTION_DAYS', DEFAULT_RETENTION_DAYS, 1, 365)
        await prune_accepted_batches(env.DB, retention_days)
