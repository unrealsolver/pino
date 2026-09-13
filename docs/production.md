# Production: application repository

[infra-contract.md](../infra-contract.md) is the canonical VPS contract. If earlier
deployment proposals or this runbook disagree with it, follow that contract. The
infrastructure repository provisions Caddy, the Python service and `pino-release`;
this repository owns application checks, release artifacts and CI delivery only.

## Agreed boundaries

- GitHub Actions builds/tests/releases the application; one native API instance runs
  on the shared VPS. Caddy serves the frontend and normalized covers with TLS.
- No production ingestion/refinement jobs or timers. The workstation publishes to the
  existing PostgreSQL endpoint and uploads covers before database references.
- API, publisher and migrations deliberately share the existing Pino owner role.
  The resulting API write/migration privilege is an accepted risk.
- Preserve the existing direct PostgreSQL firewall policy for workstation publishing.
  The API itself listens only on loopback; public/private access is enforced by Caddy.
- Ansible owns infrastructure provisioning. Routine releases invoke its `pino-release`
  helper, not a full playbook. There is only one deployment lifecycle implementation.
- API DB timeout changes remain deferred: see [database-timeouts.md](../database-timeouts.md).

## Repository tooling

| File | Responsibility |
| --- | --- |
| `.github/workflows/ci.yml` | Push/PR checks and reusable release checks: Ruff, pytest, frontend tests/build, advisory reports |
| `.github/workflows/release.yml` | Manual version, checked build, archive/install smoke test, tag and GitHub Release |
| `.github/workflows/deploy.yml` | Fetch/verify published artifact, SSH upload, invoke infrastructure helper |
| `scripts/release.py` | Stdlib packaging/identity verification; local extraction for CI install smoke tests |
| `tests/test_release.py` | Artifact validation and CI-to-infrastructure invocation tests |

The former `scripts/deploy.sh`, deployment environment example and database-schema
inspection subcommand have been removed. Do not install application-side scripts as
server deployment helpers. Infrastructure owns locking, final-path virtualenv preparation,
backups, migrations, activation, retained assets, probes and rollback.

## Release artifact

Manually select a version such as `0.1.0`. CI tests the selected commit, builds the
frontend, packages it and smoke-tests a frozen Python install before publishing the
immutable `v0.1.0` tag and GitHub Release. Versions are explicit, not inferred from commits.

One release covers frontend and backend:

- `apps/`, `packages/`, `pyproject.toml`, `uv.lock` and package installation files;
- compiled `web/dist/`, with no frontend build/runtime needed on the VPS;
- `release.json` containing the version (with `v`) and originating full Git commit.

Publish `pino-v0.1.0.tar.gz` and `pino-v0.1.0.tar.gz.sha256`. Include no secrets,
hidden paths, links, local data, caches or virtualenvs. The canonical extraction ceiling
is 2 GiB / 100,000 entries. The packer uses an allowlist of tracked Python runtime files
plus the built frontend. CI verifies the checksum and checks manifest identity against
the GitHub tag's resolved commit before sending it to infrastructure. Server verification
remains independent; CI's manifest check does not assume the helper parses `release.json`.

The tag identifies the application release; Python package metadata versions remain
independent. Existing tags/assets are never overwritten by the workflows. A publication
failure after tag creation requires inspection/completion of the draft release, not
blind tag reuse.

## GitHub setup and operation

Create a protected `production` environment with required approval and permitted trusted
workflow branches. Configure:

- variable `DEPLOY_HOST` (hostname/IPv4);
- optional variable `DEPLOY_PORT` (default 22);
- secrets `DEPLOY_SSH_KEY` and `DEPLOY_KNOWN_HOSTS`.

The remote identity is fixed to `pino-deploy`, matching the canonical contract; no
`DEPLOY_USER` variable is needed. Pin the known_hosts entry through a trusted channel,
including `[host]:port` for nonstandard ports. No runtime `ssh-keyscan` trust bootstrap.
The deployment key must be provisioned through infrastructure configuration.

Only release publishing requests contents-write permission. Normal tests do not receive
deployment secrets. Protect the default branch and published `v*` tags; enable immutable
GitHub Releases where available. Actions are commit-pinned; uv 0.10.2 and Bun 1.3.5 are
explicit. Python/JS advisory reports are visible but non-blocking for now: failures may
mean advisories or audit-tool/network failure, so inspect logs.

1. Run **Release** on a trusted ref with `version=0.1.0`.
2. Run **Deploy** with the published `version=v0.1.0`; approve the production environment.
3. CI uploads to `/home/pino-deploy/incoming/<run-id>-<attempt>/` and invokes, without sudo:

```sh
pino-release deploy v0.1.0 /home/pino-deploy/incoming/RUN/pino-v0.1.0.tar.gz \
  --sha256 SHA256_FROM_RELEASE --commit FULL_GIT_COMMIT
```

The workflow serializes deployments with `cancel-in-progress: false`; infrastructure
also holds a host lock. The CI job has a 20-minute outer limit. Infrastructure owns
individual command deadlines; confirm those against anticipated migration duration.
An explicit cancellation, SSH loss or outer timeout requires inspecting host state.

## Server behavior and recovery

Follow the canonical contract for provisioning and permissions. It uses root-owned uv
in `/opt/pino-tools` and OS Python 3.12+, with isolated final-path release virtualenvs
and a persistent uv cache. The non-login API user cannot modify releases/cache/media.
Service control goes through infrastructure's fixed helper, not unrestricted sudo.

`pino-release` snapshots/verifies uploads, prepares releases and retains hashed assets
at `/opt/pino/static/assets`. Before stopping Pino it creates a custom-format database
dump under `/opt/pino/backups`. It migrates, switches the `current` symlink, starts Pino
and probes local health plus public API/SPA/assets/covers. No Caddy reload is needed.
First-start enablement and IaC status registration are also infrastructure-owned.

Use `pino-release rollback v0.1.0` for an installed schema-compatible release.
Infrastructure checks compatibility before stopping the service; it never downgrades
the DB. Failed health automatically restores the previous release only with unchanged
DB revision, and deployment still fails. Failed/interrupted migrations or failed health
after a schema change require operator recovery. Keep `current` and `previous` targets.

Inspect `systemctl status pino-api.service`, `journalctl -u pino-api.service` and the
release symlinks with an authorized operator account. Local dumps are not off-host
backups: copy dumps/media off-host, test scratch restoration and arrange retention/alerts.
Pause workstation publishing during schema changes and resume with compatible code.
Use immutable cover filenames, upload covers first, and never use destructive live
media synchronization. No automatic cleanup is implemented by app CI.

## Verification boundary

Local tests validate our archive format, identity checks, installation and exact helper
invocation, not the infrastructure implementation. Before go-live run the canonical
contract's infrastructure tests and real AlmaLinux/SELinux, Caddy/TLS, permissions,
database publishing, backup/restore and Ansible convergence checks.

The API has a 10-second response-generation deadline, safe DB error responses and a
bounded per-process rate limiter. The HTTP deadline does not stop synchronous DB work.
Edge rate limiting and API connection-specific DB limits remain deferred as recorded
in the canonical contract; do not describe them as deployed protections.
