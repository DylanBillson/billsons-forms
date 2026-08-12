# Billson's Forms 2.0

Billson's Forms is a self-hosted FastAPI form backend with a small authenticated management interface. Public submissions are validated and accepted into a PostgreSQL queue; a separate worker delivers them through each endpoint's SMTP configuration. Submission bodies are never written to ordinary logs and queued payloads are encrypted at rest.

## Production architecture

The production [docker-compose.yml](docker-compose.yml) runs five services:

- `db`: PostgreSQL 17 with a real database healthcheck.
- `migrate`: a one-shot configuration check followed by `alembic upgrade head`.
- `app`: two Uvicorn workers, reachable only through Traefik on the external `edge` network.
- `worker`: claims queued delivery jobs with PostgreSQL row locking and sends email outside the API process.
- `cleanup`: applies data-specific retention policies on a configurable interval.

The application has no production host-port mapping. The Compose file deliberately retains the deployment's Traefik entrypoint name `websecure` and certificate resolver name `letsencrypt`. Change those labels only if the existing Traefik installation uses different names.

## Environments

The repository supports three deliberately separate server roles:

- `dhb-server-1` is the development server and uses only `docker-compose.dev.yml`.
- `dhb-server-2` is the personal deployment and uses only `docker-compose.yml`.
- `galassify-server` is the company deployment and uses only `docker-compose.yml`.

Each server has its own uncommitted `.env`. Development values must not be copied into either deployment, and deployment secrets must not be copied back into development.

## Production deployment

Requirements are Docker Compose, an existing Traefik instance, and an external Docker network named `edge`:

```bash
docker network create edge
cp .env.example .env
```

Edit `.env` before starting. At minimum replace the database password, `APP_SECRET_KEY`, `APP_ENCRYPTION_KEY`, `BASE_URL`, `TRAEFIK_HOST`, and `TRUSTED_PROXIES`. Generate cryptographic values locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Do not reuse or commit these values. The encryption key is required to decrypt SMTP/CAP credentials and queued jobs, so back it up securely; losing it makes those encrypted values unrecoverable.

Start the published GHCR image:

```bash
docker compose pull
docker compose up -d
docker compose ps
```

The app and worker wait for PostgreSQL and for the one-shot migration service to complete successfully. Production startup fails when the database URL is not PostgreSQL, secrets are malformed/placeholders, debug or insecure cookies are enabled, `BASE_URL` is not HTTPS, or trusted proxy configuration is invalid.

Create the first administrator after startup:

```bash
docker compose run --rm app python -m app.scripts.create_admin
```

Passwords must be at least 12 characters and must not contain the username.

## Development on dhb-server-1

[docker-compose.dev.yml](docker-compose.dev.yml) is a complete standalone development stack. It builds the `development` Docker target, bind-mounts the repository, enables Uvicorn reload, publishes `localhost:8000`, runs its own PostgreSQL 17 volume, and attaches the app to the external Traefik `edge` network. It is never combined with the production Compose file.

The uncommitted development `.env` should contain development-specific values, including:

```dotenv
APP_ENV=development
BASE_URL=https://forms.billson.xyz
TRAEFIK_HOST=forms.billson.xyz
TRUSTED_PROXIES=172.18.0.0/16
```

`172.18.0.0/16` is the current external edge-network subnet on `dhb-server-1`; re-check it with `docker network inspect edge` if that network is recreated. Supply local database credentials and generated application secrets as well. Never commit `.env`.

Start, inspect, follow logs, and stop the stack with:

```bash
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml ps
docker compose -f docker-compose.dev.yml logs -f
docker compose -f docker-compose.dev.yml down
```

Create the initial development administrator from the locally built image:

```bash
docker compose -f docker-compose.dev.yml run --rm app python -m app.scripts.create_admin
```

The profiled `test` service is not started by `up`. Run the authoritative test workflow explicitly:

```bash
docker compose -f docker-compose.dev.yml run --rm test
```

For a local Python environment:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

On Windows, activate with `.venv\Scripts\activate`. The `.dockerignore` excludes `.env`, Git data, virtual environments, caches, tests, runtime data, local databases, documentation, and other build-only files from image context. `requirements-dev.txt` remains in the build context solely for the explicit development target; the production target installs only `requirements.txt` and copies only runtime application/migration files.

## Traefik and client IPs

Traefik terminates HTTPS, applies HSTS and an absolute request-body ceiling, and forwards to container port 8000. Uvicorn proxy-header rewriting is disabled. The application itself accepts `X-Forwarded-For`/`X-Real-IP` only when the immediate network peer belongs to `TRUSTED_PROXIES`; otherwise it uses the socket peer and ignores forwarded values.

Set `TRUSTED_PROXIES` to the actual CIDR used by the external Traefik `edge` network, or to explicit Traefik container IPs. Do not use a generic Docker/private supernet. Production validation rejects catch-all and obviously broad private ranges. Determine the real subnet with:

```bash
docker network inspect edge --format '{{(index .IPAM.Config 0).Subnet}}'
```

If `edge` has multiple IPAM entries, inspect the full JSON and list each subnet that can directly originate application connections. Re-check this value whenever the external network is recreated.

## Health and migrations

- `GET /api/health` is lightweight liveness and only confirms that the process can answer.
- `GET /api/ready` checks PostgreSQL and returns `503` while the application cannot safely serve traffic.

Docker uses readiness for the application healthcheck and `pg_isready` for PostgreSQL. Schema changes are run once by `migrate`, rather than by every application/worker container. Before upgrading, back up PostgreSQL and `.env`, pull the desired image tag, inspect release notes/migrations, and then run `docker compose up -d`. Pin `IMAGE_TAG` for controlled releases instead of relying on `latest`.

## Endpoint configuration

Endpoint create/edit uses one validation layer for:

- slug, recipient and sender email addresses;
- SMTP hostname, port, authentication and security mode;
- redirect URLs and Reply-To field names;
- CAP.js URL/site/secret requirements;
- Allowed Origins;
- payload and rate-limit bounds.

Invalid fields are returned to the same form with entered non-secret values preserved. SMTP and CAP secrets are encrypted in PostgreSQL.

### Allowed Origins and CORS

Allowed Origins contains one bare origin per line: scheme, hostname, and optional port only, for example `https://www.example.com` or `http://localhost:5173`. Only HTTP/HTTPS is accepted. Paths, queries, fragments, credentials, wildcards, `null`, malformed ports and invalid hosts are rejected. Scheme/host casing and default ports are normalized, and duplicates are removed.

When an endpoint has at least one allowed origin, a submission must contain a valid matching `Origin` header; omitting it does not bypass the allowlist. With an empty list, origin access filtering is disabled. The API handles each endpoint's OPTIONS preflight independently, echoes a permitted origin rather than using `*`, supplies allowed methods/headers, and sends `Vary: Origin`.

### CAP.js

The Verification URL must be the full siteverify endpoint, not the CAP server home/base URL. Example:

```text
https://cap.example.com/siteverify
```

CAP outcomes distinguish an accepted token, rejected token, invalid local configuration, an unavailable/timeout service, and a malformed CAP response. Public errors do not expose internal diagnostics; delivery metadata and configuration-test audit entries retain useful status detail.

### Test Configuration

The endpoint detail page provides authenticated, CSRF-protected tools:

- **Test SMTP** sends a clearly identified test message to configured recipients.
- **Test CAP.js** checks reachability and the expected siteverify response shape using dummy values; it does not claim to validate a real CAPTCHA token.

Test actions are audited without recording stored secrets.

## Submission API

```http
POST /api/v1/forms/{slug}
```

Only these media types are accepted:

- `application/json` containing an object;
- `application/x-www-form-urlencoded`.

`multipart/form-data`, files, and all other content types return `415`. The application checks the configured/absolute limit while streaming the body, so missing or misleading `Content-Length` cannot bypass it. Traefik independently caps the body using `ABSOLUTE_MAX_PAYLOAD_BYTES`.

Origin and rate-limit checks happen before body parsing. A successful validation queues an encrypted job and normally returns `202 Accepted`; endpoint redirect settings still produce a `303` redirect. Rate-limit failures return `429` with `Retry-After` and rate-limit headers.

## Delivery queue and privacy

The API resolves one immutable delivery snapshot before returning success. The encrypted snapshot includes submitted fields, recipients, sender, subject, SMTP host/port/username/password/security mode, and the resolved Reply-To address. Consequently, an accepted delivery uses exactly the configuration that was valid at acceptance time: later endpoint edits, recipient changes, disabling, or deletion cannot alter it.

Workers claim jobs with `FOR UPDATE SKIP LOCKED`, preventing duplicate concurrent processing across containers. While SMTP is running, each worker refreshes `locked_at` in independent short-lived transactions every `QUEUE_HEARTBEAT_SECONDS` (60 seconds by default). The interval must be shorter than `QUEUE_LOCK_TIMEOUT_SECONDS` (300 seconds by default). A live heartbeat prevents reclaim; an abandoned job becomes eligible after the stale-lock timeout. Completion and failure transitions verify the expected worker still owns the claim, so a worker that lost ownership cannot overwrite the legitimate new owner's state.

Temporary SMTP/network errors use bounded exponential backoff; authentication, sender, and recipient failures are terminal. Attempts and current state are visible on the endpoint detail page.

The complete encrypted snapshot is destroyed immediately after successful delivery and also removed when a failure becomes terminal. Retryable jobs retain it only while another attempt remains. Terminal job metadata is retained briefly for diagnosis, then purged. Ordinary audit/delivery logs never contain submitted fields, SMTP passwords, or message bodies.

## Authentication and web security

Passwords use Argon2. Login attempts have a database-backed limiter separate from form limits and use a generic invalid-credentials response. Sessions use random bearer tokens; only SHA-256 hashes are stored. Cookies are `Secure`, `HttpOnly`, and `SameSite=Lax` in production. Password changes and user disabling invalidate that user's existing sessions.

Every cookie-authenticated state-changing management request—including login, logout, endpoint changes/tests, and user administration—requires a cryptographically authenticated CSRF token. The public submission API is intentionally excluded. Central response middleware adds CSP, anti-framing, nosniff, referrer policy, and HSTS headers; JavaScript is served as an external file so CSP does not need `unsafe-inline`.

## Rate limiting

Each endpoint can enable/disable its submission limiter and choose request count/window values. Defaults are 30 requests per 60 seconds. Buckets use endpoint plus a hashed client identity and a PostgreSQL atomic upsert, so multiple Uvicorn workers or application containers share one race-safe limit. Login uses its own default of 10 attempts per 15 minutes.

## Retention and cleanup

Defaults are deliberately data-specific:

| Data | Setting | Default |
|---|---|---:|
| Delivery metadata logs | `DELIVERY_LOG_RETENTION_DAYS` | 365 days |
| Audit logs | `AUDIT_LOG_RETENTION_DAYS` | 730 days |
| Expired sessions | `EXPIRED_SESSION_RETENTION_DAYS` | 30 days after expiry |
| Expired rate buckets | `RATE_LIMIT_RETENTION_HOURS` | immediately eligible |
| Terminal queue job metadata | `QUEUE_TERMINAL_RETENTION_DAYS` | 7 days |

The `cleanup` service runs every `CLEANUP_INTERVAL_SECONDS` (one hour by default). A one-off cleanup is also available:

```bash
docker compose run --rm cleanup python -m app.scripts.cleanup
```

## Configuration reference

Operational settings and defaults are listed in [docs/settings_registry.md](docs/settings_registry.md) and [.env.example](.env.example). Queue retry count/poll/lock timing, SMTP timeout, session lifetime, proxy networks, request ceilings, rate limits, and each retention lifetime are environment-configurable.

## Tests and CI

Fast tests may use isolated SQLite databases while developing a unit in isolation:

```bash
pip install -r requirements-dev.txt
pytest -m "not postgres"
```

SQLite is not considered sufficient evidence for queue row locking, heartbeat/stale-claim recovery, foreign-key deletion behavior, or atomic rate-limit concurrency. The authoritative local workflow is the standalone development Compose test service:

```bash
docker compose -f docker-compose.dev.yml run --rm test
```

That service runs `python -m app.scripts.test`. The bootstrap requires `TEST_DATABASE_URL`, requires PostgreSQL, refuses any database name without `test`, terminates existing connections to the disposable database, recreates it, runs `alembic upgrade head`, and then runs the complete pytest suite with both `DATABASE_URL` and `TEST_DATABASE_URL` targeting that database. PostgreSQL-specific tests therefore execute rather than silently falling back to SQLite.

For a direct host-Python reproduction, provide a disposable PostgreSQL 17 `TEST_DATABASE_URL` whose database name contains `test`, install `requirements-dev.txt`, and invoke the same command:

```bash
python -m app.scripts.test
```

The database is dropped and recreated, so never point this command at a retained or production database. SMTP and CAP are mocked; tests never send real mail or contact production verification services. GitHub Actions runs a lightweight unit job and this complete PostgreSQL 17 workflow, and requires both before the production-target image can be published.

## Backups and recovery

Back up the PostgreSQL volume with PostgreSQL-native tools and separately protect `.env`/secret-manager values, especially `APP_ENCRYPTION_KEY`. Restore the database and the matching encryption key together. Queue payloads present at backup time are encrypted, but backups still contain sensitive ciphertext and should receive the same access controls as production data. Test restore and upgrade procedures regularly.

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
