# Production deployment contract

Pino serves a read-only event API and a static React frontend. Ansible owns provisioning,
nginx/TLS/access control, the API systemd service, permissions and backups. This document
does not install or change server infrastructure.

This is the handoff specification for the application CI/deploy implementation and the
separate Ansible repository. Preserve the decisions below; ask before architectural
additions. Keep it small: no containers, custom deployment platform, application auth
framework, custom WAF or CAPTCHA in this scope. Infrastructure examples are requirements
to implement and test, not evidence that the VPS is already configured.

## Go-live decisions

Confirmed:

- CI: GitHub Actions.
- Runtime: one Pino instance on a Linux VPS, shared with other services.
- Production runs only the API and static serving (frontend and cached covers): no
  ingestion, refinement, scheduled jobs or Pino timers.
- Infrastructure: managed separately with Ansible.
- Reverse proxy: existing nginx with TLS on the VPS; reuse it.
- Routine application releases must not require the full infrastructure playbook.

### Versioned releases and routine redeploy — decided, not yet implemented

Use a manually triggered GitHub Actions deployment and one small server-side release
script. No containers, deployment service or zero-downtime machinery for now; accept
a brief API interruption during restart. Ansible provisions the script's prerequisites,
service units, directories, credentials and narrowly scoped restart permissions.

1. Manually trigger a release with an explicit version such as `0.1.0`. CI tests the
   selected commit and builds the frontend from frozen lockfiles. On success, create
   the immutable `v0.1.0` tag and GitHub Release with one `pino-v0.1.0.tar.gz` artifact.
   Versions are selected explicitly, not inferred from commit messages. Existing tags
   and published artifacts must never be overwritten.
2. Deploy that published artifact immediately or later, without rebuilding it. Upload
   over SSH to `/opt/pino/releases/v0.1.0/`. Prepare its Python environment there using
   the frozen lockfile before stopping the running release; never update a running
   release's files or environment in place.
3. Under a host-side deployment lock, stop the Pino API, then run migrations using the
   **new release** and a separate migration credential.
   Do not restart nginx or touch unrelated VPS services.
4. Atomically switch `/opt/pino/current` to the prepared release and start the Pino API.
   Probe local readiness with bounded retries, then smoke-test the public event API
   and frontend through nginx.
5. Keep the previous release for rollback. If health fails and the DB revision is
   unchanged, switch back and restart. After a schema change, stop and require an
   operator decision; do not automatically downgrade the database. Report deployment
   failure even if rollback succeeds.

Serialize deployments in CI as well as on the host; a new release must not cancel one
mid-migration. Re-deploying the same version should reuse its completed release directory,
not mutate a running release. Preserve old hashed frontend assets as described below.
Use a dedicated deploy identity, verify the SSH host key, and limit elevated permissions
to Pino operations. Provision resource limits for Pino's services on this shared VPS.

Implementation still needs the production hostname/access policy and concrete SSH/service
identities. No GitHub Actions workflow or deployment script has been added yet.

### Artifact contents and FE/BE delivery

One version covers both frontend and backend. The archive contains `web/dist/`, the
Python workspace (`apps/`, `packages/`, `pyproject.toml`, `uv.lock`) and any files needed
to install those packages. Exclude secrets, local data, caches and virtual environments.

- Frontend: nginx serves `/opt/pino/current/web/dist` directly. No Node/Bun runtime or
  nginx restart is needed for an application release. Retain previous hashed assets
  for already-open tabs, as described below.
- Backend: create a virtualenv inside each release and restart the API through
  `/opt/pino/current/.venv/bin/pino-web` after switching releases.
- Configuration, database and covers live outside release directories.

`current` is a symlink, not a mount. Under the deployment lock, create a temporary
symlink next to it and rename over it atomically (Linux):

```sh
ln -s /opt/pino/releases/v0.2.0 /opt/pino/current.next
mv -Tf /opt/pino/current.next /opt/pino/current
```

The temporary name must be unused; stop on errors. Switching the symlink does not
change the already-running API process, so the stop/start steps above remain required.
Rollback uses the same switch to the previous release, subject to schema compatibility.

### Python environments and cache

Keep one persistent uv cache at `/var/cache/pino/uv`, writable by the deployment user,
and a separate `.venv` inside every release. From the final release directory, run:

```sh
UV_CACHE_DIR=/var/cache/pino/uv uv sync --frozen --all-packages --no-dev
```

The shared cache avoids repeated dependency downloads/builds; virtualenvs stay isolated
so preparing a release cannot alter the running one. Create each virtualenv at its final
absolute path and never move it afterward. Keep the current and previous releases;
clean older inactive releases separately from cache maintenance. No virtualenv is
shipped from CI, and no shared mutable virtualenv is used across releases.

How event data and normalized covers reach production remains a separate decision.
The serving deployment does not ingest or refine them. One-off schema migrations are
release operations, not production background jobs.

## VPS identities and isolation

Use separate deployment and runtime identities. Names below are proposed concrete
defaults; reconcile them with the existing Ansible inventory.

| Identity | Required access | Must not have |
| --- | --- | --- |
| `pino-deploy` | SSH release delivery; write `/opt/pino` and `/var/cache/pino/uv`; start/stop/restart only the Pino API unit; release migration credential | Unrestricted sudo, other services' credentials or writable service units |
| `pino` | Non-login API account; read/execute release files and its API config; read-only DB credential | SSH keys/login, sudo, write access to releases/cache/`current`, migration credential |
| Existing nginx user | Traverse release parents; read frontend files and normalized covers | Pino secrets, write access to release/media files |

Ansible/root owns `/etc/pino`, systemd units and any privileged helper. Scope sudo to
specific systemctl actions on the chosen Pino unit; do not grant a root shell or run
deploy-writable scripts/Python code as root. Migrations run without OS root privileges.
The deploy identity is trusted to replace application code; its compromise can affect
Pino and its database, even though it must not grant control of other VPS services.

Keep API and migration secrets in separate files/environments with restrictive modes;
never expose the migration credential to the API service. Other services' secrets must
also have restrictive permissions, not be world-readable. Do not put private config
under nginx's document root. The API need not read cover files when nginx serves them.

A Linux account is not a one-directory jail: world-readable system files remain readable.
Use normal ownership/permissions plus a systemd service sandbox, not a chroot for now.
Baseline API unit settings to verify on the target host:

```ini
[Service]
User=pino
Group=pino
WorkingDirectory=/opt/pino/current
ExecStart=/opt/pino/current/.venv/bin/pino-web --config /etc/pino/api.yaml --no-migrate
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
```

This is a fragment, not a complete unit: add the private API environment, restart policy,
resource limits and normal installation settings through Ansible. Filesystem protection
restricts writes, not all reads. The serving API needs no persistent writable directory;
logs go to the journal. Ensure Python/uv-managed interpreter paths are accessible outside
protected home directories, and keep the runtime out of deploy/cache ownership groups.
Set `MemoryMax`, `CPUQuota` and `TasksMax` according to VPS capacity, leaving headroom for
the other services. See [systemd execution sandbox documentation](https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml).

### Host and CI security baseline

- Preserve existing services/firewall rules. Expose this app only through nginx HTTP/HTTPS;
  restrict SSH to trusted access where feasible. Never publicly expose Pino's API port
  or PostgreSQL. Use SSH keys, disable password/root SSH login after verifying admin access.
- CI uses a dedicated deployment key and a verified SSH host key. Keep secrets out of
  pull-request/untrusted-code jobs. Give release publishing write permissions only where
  needed; test/build jobs do not need deployment credentials. Pin toolchain/action versions.
- Apply Linux/nginx security updates and dependency audits in CI. The earlier Python
  audit is a snapshot, not a permanent guarantee; frontend advisories remain an explicit
  follow-up without package overrides. Make advisory handling visible, not silently ignored.
- Keep off-host database/media backups and test restoration. Alert on downtime, disk
  pressure, repeated deployment failures and unusual error/traffic spikes; bound log retention.
- Public scraping cannot be eliminated by rate limits. If volume saturates the VPS link,
  protection must be upstream (hosting provider or optional CDN/WAF), not application code.

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
Nginx and the API need only read/traverse permission; publishing covers is outside the
serving runtime. Do not enable
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
and absolute paths for mutable data; keep media, DB files (if SQLite)
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
Ansible-managed environment/secrets, not command-line arguments. Do not deploy source/LLM
credentials or Telegram sessions to the serving runtime.

## Migrate, start, verify

Back up the database before deploying. Run migrations once with a migration-capable DB
role and the target release installed; do not have multiple service processes migrate
concurrently:

```sh
/opt/pino/releases/v0.2.0/.venv/bin/pino db upgrade --config /etc/pino/migrate.yaml
/opt/pino/current/.venv/bin/pino-web --config /etc/pino/api.yaml --no-migrate
```

`--no-migrate` checks the Alembic version and refuses startup if it differs from the
application revision, without performing DDL. Use it for the API systemd service;
development retains automatic migration. The API DB role can have read-only table
access (including `alembic_version`). The release migration command uses a separate
credential unavailable to the API service. Connections are checked before pool reuse.
The migration example deliberately uses the new release directly, before switching
`current`; start the API only after that switch. Ensure a backup/recovery path exists
before migrations. If migration fails, do not activate the release or assume the old
schema is intact; inspect the revision/state before restarting or rolling back.

For the API only, include `connect_timeout=5` in its PostgreSQL connection URL and set
role-level `statement_timeout = '5s'` and `lock_timeout = '1s'` through Ansible.
Do not apply these short query limits to migrations or ingestion roles. A nginx timeout
does not cancel a database query; [PostgreSQL statement/lock timeouts](https://www.postgresql.org/docs/current/runtime-config-client.html#GUC-STATEMENT-TIMEOUT)
bound the work at the database. These are not total request deadlines: pool waits,
multiple statements and Python processing can add time. The API returns a generic JSON
503 for SQLAlchemy database failures and logs the exception server-side.

Systemd should restart the API on failure and capture stdout/stderr. Do not provision
Pino ingestion/refinement services or timers on the production VPS.

After starting, check `/api/health` for HTTP 200 and `{"status":"ok"}`. It checks DB
connectivity and returns a generic 503 on failure. Also smoke-test `/api/events?limit=1`,
`/event/`, a hashed frontend asset, and one cached cover through nginx; confirm content
types, cache headers, intended authentication and trusted proxy client addresses.

Back up the production database and media. Keep the preceding
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

## Receiving-agent checklist

Before implementing, resolve:

- Production hostname, public versus private access, SSH destination/port and trusted host key.
- Existing nginx/systemd conventions, final unit/user names, Linux/systemd version and
  CPU/memory budget. Do not alter unrelated VPS services.
- PostgreSQL location, database/role provisioning and secret delivery. Production
  deployment guidance targets PostgreSQL; SQLite remains a development fallback.
- How externally prepared event data and covers are published, and coordination with
  schema-changing deployments. Do not invent ingestion jobs on the serving VPS.
- Backup destination/retention, alert recipient and CI advisory policy.

Deliverables:

1. GitHub Actions checks and versioned release publishing, with an artifact checksum
   and the originating commit recorded. Verify the uploaded artifact before extraction;
   reject unsafe paths and invalid version names. Never unpack as root or over a live release.
2. Manual deployment of a published version using a small script, with host/CI locking,
   bounded preparation/probes and clear failure/rollback output. Incomplete release
   directories must not be mistaken for reusable completed releases.
3. Separate Ansible integration for users/permissions, persistent cache/media/config,
   Python/uv, hardened API unit, existing nginx/TLS integration, firewall and DB limits.
   Routine deployment must not rerun the full playbook.
4. A short operator runbook: release, deploy, inspect logs/status, rollback and recover
   from failed migrations. Include cleanup without deleting active/rollback releases.

Acceptance checks on the actual VPS:

- Frozen dependency install works as the deploy user; the runtime can execute the
  final-path virtualenv but cannot change code, `current`, cache or migration secrets.
- Health and a real event query pass with the read-only DB role; outdated schema blocks
  startup; a DB outage yields a safe error; API timeouts and nginx 429s are observable.
- API/DB ports are not public. Private-site protection covers API, frontend and media
  if chosen; public health probes and secret/dotfile paths are denied.
- New frontend/backend are active together after restart. Test old hashed asset URLs
  after switching: merely keeping an old release directory does not route those URLs.
  Implement an nginx fallback or retained static asset store without mutating releases.
- Deploy/redeploy/compatible rollback work, concurrent deploys are rejected or serialized,
  failed probes produce a failure result, and unrelated VPS services remain running.
- Backup restoration and the schema-changing failure procedure are verified before go-live.
