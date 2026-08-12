# Settings registry

Environment variables are the source of deployment configuration. Production values belong in `.env` or a deployment secret manager and must never be built into the image.

| Variable | Default | Purpose |
|---|---:|---|
| `APP_NAME` | `Billson's Forms` | Display/application name. |
| `APP_ENV` | `development` | Set to `production` to enable startup sanity checks. |
| `APP_DEBUG` | `false` | FastAPI debug mode; forbidden in production. |
| `APP_SECRET_KEY` | development placeholder | HMAC/CSRF application secret; production requires 32+ non-placeholder characters. |
| `APP_ENCRYPTION_KEY` | development placeholder | Fernet key for SMTP/CAP secrets and queued payloads; production requires a generated key. |
| `BASE_URL` | `http://localhost:8000` | Public base URL; HTTPS is required in production. |
| `DATABASE_URL` | local Compose URL | SQLAlchemy PostgreSQL URL. |
| `TRUSTED_PROXIES` | loopback only | Comma-separated actual proxy-network CIDRs or explicit proxy IPs trusted to supply forwarded client IP headers. Broad private supernets are rejected in production. |
| `SECURE_COOKIES` | `true` | Secure session/CSRF cookies; required in production. |
| `SESSION_LIFETIME_HOURS` | `336` | Login session lifetime. |
| `LOGIN_RATE_LIMIT_REQUESTS` | `10` | Login attempts per login window and client IP. |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `900` | Login limiter window. |
| `DEFAULT_FORM_RATE_LIMIT_REQUESTS` | `30` | Suggested/default per-endpoint submission count. |
| `DEFAULT_FORM_RATE_LIMIT_WINDOW_SECONDS` | `60` | Suggested/default per-endpoint submission window. |
| `ABSOLUTE_MAX_PAYLOAD_KB` | `1024` | Application hard ceiling; endpoint limits may be lower. |
| `ABSOLUTE_MAX_PAYLOAD_BYTES` | `1048576` | Matching Traefik buffering ceiling in Compose. Keep consistent with the KB value. |
| `SMTP_TIMEOUT_SECONDS` | `20` | Timeout for synchronous SMTP work executed in a worker thread. |
| `QUEUE_MAX_ATTEMPTS` | `6` | Maximum worker attempts before terminal failure. |
| `QUEUE_POLL_SECONDS` | `2` | Idle worker polling interval. |
| `QUEUE_LOCK_TIMEOUT_SECONDS` | `300` | Time after which a processing claim is considered stale. |
| `QUEUE_HEARTBEAT_SECONDS` | `60` | Worker heartbeat interval; must be shorter than the stale-lock timeout. |
| `DELIVERY_LOG_RETENTION_DAYS` | `365` | Delivery metadata lifetime. |
| `AUDIT_LOG_RETENTION_DAYS` | `730` | Audit event lifetime. |
| `EXPIRED_SESSION_RETENTION_DAYS` | `30` | Grace period after session expiry. |
| `RATE_LIMIT_RETENTION_HOURS` | `0` | Grace period after bucket expiry. |
| `QUEUE_TERMINAL_RETENTION_DAYS` | `7` | Delivered/terminal failed job metadata lifetime; payloads are destroyed earlier. |
| `CLEANUP_INTERVAL_SECONDS` | `3600` | Automatic retention cleanup interval. |

The `settings` database table retains UI/application registry values such as site name and public URL, but security and deployment policy is intentionally controlled by environment variables so invalid production configuration can be rejected before the application starts.
