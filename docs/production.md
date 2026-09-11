# Production deployment contract

Pino serves a read-only event API and a static React frontend. Ansible owns deployment,
nginx/TLS/access control, systemd services/timers, permissions and backups. This document
does not install or change server infrastructure.

## Access and routing

Decide whether the site is public before exposing it. Pino has no application login:
the event API returns source text, summaries, source names, IDs, links and image URLs.
For private use, protect **all** of `/`, `/api/` and `/media/` with nginx authentication
or a VPN. Public use means deliberately publishing this data. Keep the API listener
bound to `127.0.0.1:8765`; do not expose it directly through the firewall.

Nginx must serve only `web/dist`, never the repository or its `.env`/config/session files.
The SPA requires fallback to `/index.html` for `/event/` and other frontend routes.
Serve `/assets/` from the build directory with a one-year immutable cache; serve
`index.html` with `Cache-Control: no-cache`. Keep the previous release's hashed assets
available during rollout so open browser tabs do not fail on old asset URLs.

Proxy `/api/` to `http://127.0.0.1:8765` **without stripping `/api`**. Overwrite
`X-Forwarded-For` with `$remote_addr` and `X-Forwarded-Proto` with `$scheme`, and forward
`Host $host`. Uvicorn trusts loopback by default; for a separate trusted proxy set
`FORWARDED_ALLOW_IPS` to its explicit address, never `*`. See the
[nginx proxy documentation](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass).
Block public access to `/docs`, `/redoc` and `/openapi.json` unless intentionally exposing them.

Map `/media/` to a persistent media directory. Disable directory listings and serve only
normalized `*.webp` files; send `Cache-Control: public, max-age=31536000, immutable`.
The worker needs write permission, nginx needs read/traverse permission. Do not enable
`--serve-media` in production. Its purpose is local development.

The in-process API limiter is a bounded best-effort 60 requests/minute/client guard;
its counters are per process and reset on restart. Use nginx limits for public traffic
and global resource protection. `/api/health` is exempt from the app limiter.

Keep `/api/health` private at nginx (loopback or an explicit monitoring allowlist),
and probe it locally with `curl --fail --max-time 5 http://127.0.0.1:8765/api/health`.
It makes a DB query: exposing it without a limit would bypass the event limiter.
A failed readiness probe should alert/remove traffic, not continuously restart an
otherwise healthy process during a database outage.

All `/api` and `/api/` requests, including readiness, have a 10-second application
deadline to produce a response, returning JSON 504 (`Request timed out`) with no-store
headers. Media and non-API routes are excluded. Current API responses are non-streaming
JSON; this is not a deadline for network transfer or future streaming response bodies.
The deadline does not kill synchronous worker threads or their DB queries, and depends
on a responsive event loop. Keep the shorter DB limits below and nginx protection.

For a small public deployment, start with the following nginx limits and tune against
real traffic. The per-IP burst accommodates a page load; the server-wide limit also
bounds traffic from many IPs. These are deployment settings, not applied by this repo.

```nginx
# http context
limit_req_zone $binary_remote_addr zone=pino_ip:10m rate=1r/s;
limit_req_zone $server_name zone=pino_total:1m rate=10r/s;

# Inside the existing location /api/ proxy block
limit_req zone=pino_ip burst=60 nodelay;
limit_req zone=pino_total burst=20 nodelay;
limit_req_status 429;
client_max_body_size 1k;
client_body_timeout 5s;
proxy_connect_timeout 3s;
proxy_read_timeout 15s;
```

Use an exact `location = /api/health` with the monitoring allowlist and the same proxy
headers. Keep nginx request-header size/time limits enabled; app validation occurs only
after nginx/ASGI have parsed the request. See [nginx request limiting](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html).

## Build and runtime

Build from committed lockfiles using Python 3.12+ and Bun (currently tested with 1.3.5):

```sh
uv sync --frozen --all-packages
cd web
bun install --frozen-lockfile
bun run test
bun run build
```

Deploy `web/dist` to nginx, and the Python environment/application to the service host.
Run the built frontend, not Vite's development server. Use an explicit working directory
and absolute paths for mutable data; keep media, Telegram sessions, DB files (if SQLite)
and secrets outside versioned release directories.

Minimal API configuration (source/LLM credentials are unnecessary for serving):

```yaml
storage:
  use: production
  production:
    type: postgres
    url: env:PINO_DATABASE_URL
media:
  directory: /var/lib/pino/media
  public_url: /media
```

Preserve the same refinement taxonomy settings as ingestion. Supply the DB URL through
Ansible-managed environment/secrets, not command-line arguments. Use the full source/LLM
configuration only for scheduled `pino check` and `pino refine` workers.

## Migrate, start, verify

Back up the database before deploying. Run migrations once with a migration-capable DB
role and the target release installed; do not have multiple service processes migrate
concurrently:

```sh
/opt/pino/current/.venv/bin/pino db upgrade --config /etc/pino/worker.yaml
/opt/pino/current/.venv/bin/pino-web --config /etc/pino/api.yaml --no-migrate
```

`--no-migrate` checks the Alembic version and refuses startup if it differs from the
application revision, without performing DDL. Use it for the API systemd service;
development retains automatic migration. The API DB role can have read-only table
access (including `alembic_version`); workers require write/migration permissions under
the current CLI initialization path. Connections are checked before pool reuse.

For the API only, include `connect_timeout=5` in its PostgreSQL connection URL and set
role-level `statement_timeout = '5s'` and `lock_timeout = '1s'` through Ansible.
Do not apply these short query limits to migrations or ingestion roles. A nginx timeout
does not cancel a database query; [PostgreSQL statement/lock timeouts](https://www.postgresql.org/docs/current/runtime-config-client.html#GUC-STATEMENT-TIMEOUT)
bound the work at the database. These are not total request deadlines: pool waits,
multiple statements and Python processing can add time. The API returns a generic JSON
503 for SQLAlchemy database failures and logs the exception server-side.

Systemd should restart the API on failure and capture stdout/stderr. Run one check job
at a time against each Telegram session; avoid overlapping scheduled/manual ingestion.
The CLI intentionally continues on provider/image failures, so monitor its logs rather
than relying solely on its exit status. The web service itself runs no ingestion jobs.

After starting, check `/api/health` for HTTP 200 and `{"status":"ok"}`. It checks DB
connectivity and returns a generic 503 on failure. Also smoke-test `/api/events?limit=1`,
`/event/`, a hashed frontend asset, and one cached cover through nginx; confirm content
types, cache headers, intended authentication and trusted proxy client addresses.

Back up the database, media and Telegram session state together. Keep the preceding
release for rollback, but do not blindly downgrade data: an older API rejects a newer
schema with `--no-migrate`. Restore a compatible backup or deploy a compatible fix.

## Audit scope

The predeployment audit addressed automatic API migrations, stale pooled connections,
unbounded rate-limit client state, missing readiness checks and Python dependency advisories.
Malformed/oversized event filters are rejected before querying; the 370-day window is
enforced exactly, including partial days. Datetime boundary years 1 and 9999 are rejected
to allow safe timezone and overnight schedule arithmetic.
The Python environment audit found no known third-party vulnerabilities; frontend
transitive advisories remain deferred to CI without dependency overrides.
Existing UI regressions were deliberately outside scope. Unit/build checks do not replace
the final nginx/TLS/permissions and PostgreSQL smoke tests on the target host.
