# Migration to FastAPI and Pydantic

The public contract is unchanged:

- `POST /v1/submissions`;
- `GET /v1/health`;
- schema version 1;
- the same D1 tables and migration;
- the same random batch-ID retry semantics;
- the same server-side allowlist normalization;
- the same scheduled pruning and rate-limit binding.

The previous hand-written Python request parser and `schema.py` module have
been removed. They are replaced by:

- `src/models.py`, containing Pydantic request and response models;
- `src/app.py`, containing the FastAPI routes, middleware, and exception
  handlers;
- a minimal Cloudflare `WorkerEntrypoint` in `src/entry.py` that delegates to
  Cloudflare's ASGI adapter.

Pydantic now owns required-field checks, forbidden extras, UUID/date parsing,
finite dimensions, strict integers, string patterns, and field bounds. Only
cross-field domain rules and privacy normalization remain custom application
logic.

No netlab client, D1 migration, or submission-payload change is required.
