# Pino on the shared VPS

This directory provisions Pino's native Python API, static frontend/media through the
existing Caddy, and a deployment helper. It reuses the existing `pino` database and owner
role on shared PostgreSQL. The current direct PostgreSQL firewall policy stays intact.
Ingestion and publishing run on the operator workstation. Database timeout changes are
deferred in [database-timeouts.md](database-timeouts.md).

## Configure and provision

Copy [config.example.yml](config.example.yml) to `local/server/pino.yml`, then fill in
the hostname, explicit `public` or `private` access, and CI/workstation SSH public keys.
The database password continues to come from `local/server/postgres.yml`; do not duplicate
it in the Pino configuration. Keep the refinement taxonomy consistent with the publisher.

For private access, generate a bcrypt hash with `caddy hash-password`. Set `auth_user`,
`auth_hash`, and the corresponding `smoke_password` in the local secret file. Caddy protects
frontend, API, assets and media. The smoke password is needed only by the deploy user.

Push secrets using the normal `push-secrets.yml` playbook, sync this repository to the VPS,
and run `iac-apply.service`. Bootstrap also transfers the optional Pino configuration.
The fallback secret-transfer manifest does not include optional Pino configuration; use
the Ansible path for this tenant.

Provisioning installs root-owned uv 0.10.2 in `/opt/pino-tools` and uses the OS Python 3.12+
for release virtualenvs. It installs a root-owned service helper with only fixed Pino
start/stop operations. Release preparation and migrations run as `pino-deploy`.
The non-login `pino` account cannot modify releases, the uv cache or media.

Before a first release, the API is neither started nor included in managed-unit status.
The first successful service start enables the unit and registers it with IaC status.
Until then the configured site has no application to serve. Subsequent Ansible applies
preserve `current` and data, and only restart Pino when its unit/configuration changes.

## Deploy a published release

The **application repository** must test/build and publish an immutable GitHub Release
containing `pino-vX.Y.Z.tar.gz`, its SHA-256 checksum and originating full Git commit.
The archive has `apps/`, `packages/`, `web/dist/`, `pyproject.toml`, `uv.lock`, and package
installation files at its root. Include actual files/directories, no symlinks, hard links,
hidden paths, secrets or virtualenvs. Maximum extracted size is 2 GiB / 100,000 entries.
App GitHub Actions workflows are not installed by this infrastructure repository.

Upload the published archive with SSH/SCP using a verified host key:

```sh
scp pino-v0.1.0.tar.gz pino-deploy@VPS:/home/pino-deploy/pino-v0.1.0.tar.gz
ssh pino-deploy@VPS pino-release deploy v0.1.0 /home/pino-deploy/pino-v0.1.0.tar.gz --sha256 SHA256_FROM_RELEASE --commit FULL_GIT_COMMIT
```

CI must serialize deployments for this VPS with `cancel-in-progress: false`. The helper
also takes a nonblocking host lock and rejects concurrent runs. Uploading does not need
that lock; extraction, preparation and activation do. Invoke the helper without sudo.

The helper verifies a snapshot of the upload, creates a final-path virtualenv from the
lockfile, retains hashed assets, and writes a completion marker. An existing completed
version must match the supplied checksum and commit and is reused without reinstalling.
Incomplete directories are deliberately left unmarked and require operator inspection.

Before stopping the API, the helper makes a custom-format `pg_dump` in
`/opt/pino/backups` (deploy-only access). It then stops only Pino, runs the new release's
migrations, switches `current`, starts the API, and probes local health and public routes.
Public smoke tests cover a real API query, SPA, asset and a cover when available. Publish
at least one cover and verify it before go-live. Routine releases do not reload Caddy or
run Ansible. Bounded commands fail rather than hanging indefinitely.

## Publish data and covers

Use the existing workstation publisher with the direct PostgreSQL endpoint and the shared
Pino credential. The production API uses the same role through loopback. That role owns
Pino's schema; loss of the Pino database after API compromise is an accepted tradeoff.
It has no superuser, database-creation or role-creation privileges.

Upload normalized `.webp` covers to `/var/lib/pino/media` as `pino-deploy` before committing
database references. For example, run from the directory containing normalized covers:

```sh
rsync -rt --chmod=D755,F644 --include='*/' --include='*.webp' --exclude='*' ./ pino-deploy@VPS:/var/lib/pino/media/
```

Use a new filename/URL for changed cover contents. Do not use `--delete` on a live media
tree. Pause workstation publishing during schema-changing deployments, then resume using
a publisher compatible with the deployed schema. No ingestion service/timer is installed.

## Inspect, rollback and recover

```sh
systemctl status pino-api.service
journalctl -u pino-api.service -n 100
readlink -f /opt/pino/current
readlink -f /opt/pino/previous
```

As `pino-deploy`, use `pino-release rollback v0.1.0` for an installed, schema-compatible
release. The helper checks compatibility before stopping the current API; it never
downgrades the database. Failed health after deployment restores the previous release
only if the database revision is unchanged, and the deployment still returns failure.

Failed/interrupted migrations leave the API stopped. Pause publishing, inspect the schema
and logs, then deploy a compatible fix or explicitly restore a compatible backup. Failed
health after a schema change also leaves the API stopped for operator recovery. A hard
kill/power loss can leave a partially prepared release or a stopped API; inspect `current`,
its completion marker and the database before rerunning commands.

Local dumps are a pre-release recovery aid. Copy database dumps and media off-host using
the operator workstation and verify restoration into a scratch database before go-live.
Choose retention and an alert destination as part of host operations; this change does
not install an off-host backup scheduler or monitoring provider.

Keep the `current` and `previous` release targets. Remove only explicitly selected inactive
release directories after checking those symlinks and ensuring no deploy is in progress.
Retained assets in `/opt/pino/static/assets` intentionally outlive releases; do not delete
assets needed by open browser tabs. Inspect disk usage and prune inactive releases, old
dumps and the uv cache separately. Never remove a live virtualenv/cache entry by traversing
`current`; no automatic cleanup runs during deployment.

Set `enabled: false`, push secrets and reapply to stop/disable the API and remove its Caddy
site, status registration and deployment sudo permission. Releases, media, database and
the database publishing role are retained.

## Validation

```sh
python3 -m unittest discover -s services/pino/tests -v
CADDY_BINARY=/path/to/caddy python3 -m unittest discover -s services/pino/tests -v
ansible-playbook --syntax-check control-plane/ansible/playbooks/apply-local.yml
```

Tests exercise hostile archives, immutable assets, failed migrations and rollback decisions.
The optional Caddy test starts a temporary local Caddy and mock API, checks both access
policies, SPA fallback, prefix-preserving proxying, media restrictions and retained assets.

On the actual AlmaLinux VPS, verify a frozen dependency install, service sandbox/SELinux
permissions, TLS, direct publishing, backups/restoration and repeat Ansible convergence.
Confirm the API port is not public. The loopback health endpoint is private at Caddy.
Edge rate limiting is deferred; the application limiter and systemd resource limits remain.
