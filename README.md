# Netlab usage ingestion — FastAPI on Cloudflare Python Workers

A Python implementation of the anonymous netlab usage ingestion service using:

- **FastAPI** for ASGI routing and request handling;
- **Pydantic v2** for request and response models;
- **Cloudflare D1** for transactional aggregate storage;
- **Cloudflare Rate Limiting** for coarse abuse protection.

Cloudflare configuration and D1 migrations remain declarative JSON/SQL. All
application logic is Python.

> Cloudflare Python Workers are currently beta and require the
> `python_workers` compatibility flag.

## Architecture

```text
netlab usage upload
        |
        | HTTPS JSON, <= 64 KiB
        v
Cloudflare Python Worker + FastAPI
  Pydantic request validation
  finite-vocabulary normalization
  coarse rate limiting
        |
        v
Cloudflare D1 transaction
  accepted_batches: short-lived retry IDs
  usage_aggregates: aggregate rows only
```

## Validation model

`UsageSubmission` and `UsageMetric` in `src/models.py` define the complete
wire contract. Pydantic handles:

- required and forbidden fields;
- UUID-v4 batch identifiers;
- ISO dates and coarse `major.minor` versions;
- the finite set of metric dimensions;
- string formats and lengths;
- strict integer parsing and numerical limits;
- metric-list size limits.

Only domain-specific checks remain as explicit validators:

- `maximum` cannot exceed `instances`;
- the reporting period must be ordered and no longer than 366 days.

FastAPI validation errors return HTTP 400 with field locations and messages.
The response deliberately omits the rejected input value, preventing private
payload values from being reflected in an error response.

Validation is separate from privacy normalization. Even a structurally valid
custom provider, device, module, plugin, or command label is collapsed to
`_custom` or `_other` before D1 receives it.

## Project layout

```text
src/
├── entry.py       Cloudflare WorkerEntrypoint and scheduled handler
├── app.py         FastAPI application, middleware, routes, error handling
├── models.py      Pydantic request and response models
├── normalize.py   server-side anonymisation and metric combination
├── allowlists.py  finite accepted vocabulary
├── storage.py     D1 transaction, upsert, and retry deduplication
└── settings.py    bounded environment-variable settings
```

## Development

Install `uv` and Node.js, then:

```shell
uv sync --dev
uv run pytest
uv run ruff check src tests
```

Create a local D1 database and run the Worker:

```shell
uv run pywrangler d1 migrations apply netlab-usage --local
uv run pywrangler dev
```

Point the netlab client at the local endpoint:

```shell
NETLAB_USAGE_ENDPOINT=http://localhost:8787/v1/submissions \
  netlab usage upload --yes
```

## Deployment

1. Create D1:

   ```shell
   uv run pywrangler d1 create netlab-usage
   ```

2. Replace `REPLACE_WITH_D1_DATABASE_ID` in `wrangler.jsonc`.
3. Apply migrations:

   ```shell
   uv run pywrangler d1 migrations apply netlab-usage --remote
   ```

4. Deploy:

   ```shell
   uv run pywrangler deploy
   ```

5. Test `GET /v1/health` and a sample submission.
6. Enable the commented custom-domain route for `usage.netlab.tools` and deploy
   again.
7. Publish `PRIVACY.md`, `SCHEMA.md`, and the aggregate retention policy before
   accepting public submissions.

## Operational properties

- The endpoint has no embedded API key; open-source clients cannot protect a
  shared secret. The results are directional telemetry, not a census.
- Unknown labels are collapsed to `_custom` or `_other` on the server.
- D1 batch execution makes the batch-ID insert and aggregate updates atomic.
- Replaying the same `batch_id` returns `duplicate` without incrementing rows.
- A constant rate-limit key supplies coarse abuse protection without creating a
  user or installation identifier.
- No raw-payload table or request logging is included.
- A scheduled handler removes deduplication IDs after the configured retry
  window.

## Reporting

```shell
uv run pywrangler d1 execute netlab-usage --remote --file queries/summary.sql
```

The report describes aggregate observations and instances. It intentionally
cannot report unique users or installations.
