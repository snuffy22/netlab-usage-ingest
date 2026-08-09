# Netlab usage ingestion — FastAPI on Cloudflare Python Workers

A Python implementation of the anonymous netlab usage ingestion service using:

- **FastAPI** for ASGI routing and request handling;
- **Pydantic v2** for request and response models;
- **Cloudflare D1** for transactional aggregate storage;
- **Cloudflare Rate Limiting** for coarse abuse protection.

The developer and deployment workflow is **Python-only**. It does not require `uv`,
Node.js, npm, npx, Wrangler, or pywrangler. Local development uses CPython + FastAPI +
SQLite. Production deployment uses Cloudflare's REST API directly.

> Cloudflare Python Workers require the `python_workers` compatibility flag.

## Architecture

```text
Local development                         Cloudflare production
-----------------                         ---------------------
CPython virtualenv                        Python Worker / Pyodide
FastAPI + uvicorn                         FastAPI
SQLite adapter       ---- deploy ---->    D1 binding
in-memory/no-op CF bindings               Rate Limiter binding

Worker package preparation
--------------------------
.venv/bin/python -m pip
        |
        +-- pure-Python wheels from PyPI
        +-- PyEmscripten wheels from PyPI
        +-- legacy Pyodide wheels from Pyodide index
        |
        `--> python_modules/  ---- upload ----> Worker bundle
```

The local D1 adapter implements the small API surface used by `src/storage.py`:
`prepare()`, `bind()`, `first()`, `run()`, and transactional `batch()`.

## Project layout

```text
src/
├── entry.py           Cloudflare WorkerEntrypoint and scheduled handler
├── app.py             FastAPI application, middleware, routes, error handling
├── models.py          Pydantic request and response models
├── normalize.py       server-side anonymisation and metric combination
├── allowlists.py      finite accepted vocabulary
├── storage.py         D1 transaction, upsert, and retry deduplication
├── settings.py        bounded environment-variable settings
├── local_d1.py        local SQLite adapter with D1-shaped API
├── local_runtime.py   injects local bindings into FastAPI
├── migrations.py      local + remote migration runner
├── cloudflare_api.py  minimal Cloudflare REST client
├── project_config.py  reads declarative Worker configuration
├── worker_vendor.py   pip-based PyEmscripten/Pyodide dependency vendoring
└── worker_bundle.py   constructs multipart Python Worker upload

tools/
└── netlab.py          Python-only dev/deploy/database CLI

requirements-worker.txt   dependencies bundled into the Cloudflare Worker
requirements-dev.txt      local development/test/deployment dependencies
```

## Requirements

The only language runtime prerequisite is Python 3.13 or newer:

```shell
python3 --version
```

On Debian/Ubuntu/WSL, Python's `venv` module must also be installed. If
`python3 -m venv` reports that `ensurepip` is unavailable, install the distro package:

```shell
sudo apt update
sudo apt install python3-venv
```

No Python package manager needs to be installed globally. `venv` bootstraps `pip`
inside `.venv`, and every project tool is then run through that virtual environment.

`uv`, Node.js, npm, npx, Wrangler, and pywrangler are not used by this workflow.

## One-time setup

If you previously used the uv-based version of this project, leave and remove that
environment first:

```shell
deactivate 2>/dev/null || true
rm -rf .venv
rm -f uv.lock
```

Create a conventional Python virtual environment:

```shell
python3 -m venv .venv
source .venv/bin/activate
```

Upgrade the **venv's** pip and install project development dependencies:

```shell
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Verify that commands resolve inside the project virtualenv:

```shell
which python
python -m pip --version
```

`which python` should point to `.../netlab-usage-ingest-cloudflare-python/.venv/bin/python`.

Whenever you open a new shell, activate the environment before working on the project:

```shell
cd ~/netlab-usage-ingest-cloudflare-python
source .venv/bin/activate
```

## Development

Run tests and linting:

```shell
python -m pytest
python -m ruff check src tests tools
```

Create/migrate the local SQLite database:

```shell
python tools/netlab.py db migrate --local
```

Run the API locally on port 8787:

```shell
python tools/netlab.py dev
```

`dev` automatically applies pending local migrations, so the explicit migrate command
is optional after initial setup.

Point the netlab client at the local endpoint:

```shell
NETLAB_USAGE_ENDPOINT=http://localhost:8787/v1/submissions \
  netlab usage upload --yes
```

The local database defaults to `.local/netlab-usage.sqlite3`. Override it with:

```shell
python tools/netlab.py dev --db /tmp/netlab-usage.sqlite3
```

### Local-runtime caveat

Local development intentionally runs **CPython + SQLite**, not Cloudflare's
`workerd`/Pyodide runtime. This is what makes the workflow independent of Wrangler and
Node.js. Runtime-specific behavior should therefore be validated on a non-production
Worker before public rollout. Application validation, normalisation, storage SQL,
deduplication, and API behavior remain testable locally.

## Cloudflare credentials

The Python deployment CLI uses the Cloudflare REST API. Export:

```shell
export CLOUDFLARE_ACCOUNT_ID='your-account-id'
export CLOUDFLARE_API_TOKEN='your-api-token'
```

The token needs permissions sufficient for the operations you run. For the complete
workflow, grant Workers Scripts Write and D1 Write permissions.

## Create the remote D1 database

```shell
python tools/netlab.py db create
```

The command prints the database UUID and an export command. Set it in your shell:

```shell
export CLOUDFLARE_D1_DATABASE_ID='the-uuid-returned-above'
```

You can alternatively replace `REPLACE_WITH_D1_DATABASE_ID` in `wrangler.jsonc`, but
using the environment variable avoids committing account-specific IDs.

## Apply remote migrations

```shell
python tools/netlab.py db migrate --remote
```

Migrations are tracked in `d1_migrations`, so already-applied files are skipped.

## Vendor Worker Python dependencies — pip only

Cloudflare runs Python Workers under Pyodide/WebAssembly, so compiled dependencies
cannot be copied from the Linux `.venv`. The `vendor` command asks the **pip inside the
active virtualenv** to resolve wheels for the Worker target instead:

```shell
python tools/netlab.py vendor --clean
```

The command uses `python -m pip install --target python_modules` with target-platform
constraints for CPython 3.13 / PyEmscripten 2025, plus Cloudflare/Pyodide's package
index for legacy Pyodide wheels. This correctly selects pure-Python packages and
WebAssembly-compatible binary wheels rather than Linux `.so` files.

The generated `python_modules/` directory is ignored by Git and is included in the
Worker upload. It is deployment content, not a second virtual environment.

If pip reports that no compatible binary distribution exists, that dependency does
not currently provide a suitable pure-Python, PyEmscripten, or Pyodide wheel for this
Worker runtime. Do not fall back to a Linux wheel.

## Deploy

```shell
python tools/netlab.py deploy
```

The deploy command:

1. vendors Worker dependencies using the venv's `pip`;
2. packages Worker source plus `python_modules/`;
3. uploads the Python modules directly to the Cloudflare Workers API;
4. configures `DB`, plain-text settings, and `SUBMISSION_LIMITER` bindings;
5. configures the workers.dev endpoint;
6. updates the configured cron triggers.

Inspect the upload metadata and bundle without contacting Cloudflare:

```shell
python tools/netlab.py deploy --dry-run
```

Reuse an already-current `python_modules/` directory with:

```shell
python tools/netlab.py deploy --no-vendor
```

`workers_dev` in `wrangler.jsonc` controls the workers.dev endpoint. Override it for one
deployment with `--workers-dev` or `--no-workers-dev`.

After deployment, test `GET /v1/health` and a sample submission before routing public
traffic to the Worker. The CLI deliberately does not modify custom-domain routes; after
workers.dev validation, configure `usage.netlab.tools` in the Cloudflare dashboard or
via the Routes/Custom Domains API. Publish the existing `PRIVACY.md`, `SCHEMA.md`, and
aggregate-retention policy before accepting public submissions.

## Reporting

Run the aggregate report against remote D1:

```shell
python tools/netlab.py report
```

Run any SQL file:

```shell
python tools/netlab.py query --file queries/summary.sql
```

The commands print Cloudflare's D1 query result as formatted JSON.

## Operational properties

- The endpoint has no embedded API key; open-source clients cannot protect a shared secret.
- Unknown labels are collapsed to `_custom` or `_other` on the server.
- D1 batch execution makes the batch-ID insert and aggregate updates atomic.
- Replaying the same `batch_id` returns `duplicate` without incrementing rows.
- A constant rate-limit key supplies coarse abuse protection without creating a user or
  installation identifier.
- No raw-payload table or request logging is included.
- A scheduled handler removes deduplication IDs after the configured retry window.

