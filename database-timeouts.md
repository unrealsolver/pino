# Deferred Pino API database timeouts

These requirements are deferred and are not applied by the current infrastructure code.
The API, workstation publisher and migrations deliberately share one database role.
The resulting API write/migration privileges are an accepted risk for now.

For the API only, include `connect_timeout=5` in its PostgreSQL connection URL and set
connection/session-level `statement_timeout = '5s'` and `lock_timeout = '1s'` for every
API database connection. Supply these through API-specific connection configuration
(e.g. PostgreSQL connection `options`), not shared role defaults. See
[PostgreSQL connection options](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNECT-OPTIONS).
Publisher and migration connections must not inherit these short API limits. A Caddy timeout
does not cancel a database query; [PostgreSQL statement/lock timeouts](https://www.postgresql.org/docs/current/runtime-config-client.html#GUC-STATEMENT-TIMEOUT)
bound the work at the database. These are not total request deadlines: pool waits,
multiple statements and Python processing can add time. The API returns a generic JSON
503 for SQLAlchemy database failures and logs the exception server-side.


Migration safety: sharing a role does not propagate connection-specific `options` to
other connections. Keep separate API and migration URLs/environments; do not set the
short limits with ALTER ROLE/ALTER DATABASE or shared PGOPTIONS. Existing role/database
defaults still apply when connection options are omitted, so inspect them before go-live.
The API's 10-second HTTP deadline does not wrap the migration CLI. The canonical
[infrastructure contract](infra-contract.md) delegates bounded migration execution to
its pino-release helper; verify its actual deadline before long migrations. The old
application-side 120-second migration wrapper has been removed. App CI still has a
20-minute deployment job limit; cancellation may interrupt SSH and requires host-state
inspection. connect_timeout=5 limits connection setup, not migration execution time.

Acceptance: check SHOW statement_timeout and SHOW lock_timeout on fresh/reconnected API
connections and on publisher/migration connections using the same role. Verify only API
connections get 5s/1s. Do not claim migration safety from configuration files alone;
confirm the effective session settings on the target database.
