# Billson's Forms

Billson's Forms is a self-hosted form backend and management platform for websites.

Create form endpoints through a web interface, route submissions directly to email, manage users, audit activity, and maintain complete ownership of your data without relying on third-party form services.

Designed as part of the Billson Stack, Billson's Forms prioritises simplicity, self-hosting, privacy, auditability, and deployment flexibility.

## Features

### Form Endpoint Management

Create and manage form endpoints through a web interface.

Each endpoint supports:

* Custom endpoint slug
* Multiple recipient email addresses
* Per-endpoint SMTP configuration
* Reply-To field configuration
* Allowed origin restrictions
* Optional CAP integration
* Success and error redirects
* Endpoint activation/deactivation
* Soft deletion

Example endpoint:

```http
POST /api/v1/forms/contact-us
```

---

### Email Delivery

Submissions are delivered directly via SMTP.

Supported features:

* Per-endpoint SMTP settings
* STARTTLS support
* SSL/TLS support
* Custom sender name
* Custom sender address
* Multiple recipients
* Encrypted SMTP credentials

Unlike many form platforms, Billson's Forms does not require a central email provider and can integrate with existing mail infrastructure.

---

### Privacy-Focused Design

Billson's Forms is designed to minimise stored personal data.

By default:

* Form submissions are delivered by email
* Submission content is not stored in the database
* Only delivery metadata is recorded
* Audit events are logged separately

Stored delivery metadata includes:

* Timestamp
* Endpoint
* Success/failure status
* IP address
* Origin
* User-Agent
* Payload size
* Delivery error messages

This approach allows administrators to troubleshoot delivery issues while minimising retained personal data.

---

### User Management

Administrators can:

* Create users
* Edit users
* Disable users
* Assign roles

Supported roles:

* Admin
* User

---

### Audit Logging

Administrative actions are recorded in an audit log.

Examples include:

* User login
* User logout
* Failed login attempts
* Endpoint creation
* Endpoint updates
* Endpoint deletion
* User creation
* User updates
* User deactivation

Audit logs provide accountability and operational visibility.

---

### Security

Billson's Forms includes:

* Argon2 password hashing
* Secure session management
* Encrypted SMTP credentials
* Encrypted CAP credentials
* Origin restrictions
* Audit logging
* Soft deletion support
* Role-based administration

---

## Technology Stack

### Backend

* Python
* FastAPI
* SQLAlchemy
* Alembic
* PostgreSQL

### Frontend

* Jinja2 Templates
* HTML
* CSS

### Infrastructure

* Docker
* Docker Compose
* GitHub Container Registry (GHCR)

---

## Quick Start (Docker)

Pull the latest image:

```bash
docker pull ghcr.io/dylanbillson/billsons-forms:latest
```

Example Docker Compose:

```yaml
services:

  app:
    image: ghcr.io/dylanbillson/billsons-forms:latest
    container_name: billsons_forms_app
    env_file:
      - .env
    depends_on:
      - db

  db:
    image: postgres:17
    container_name: billsons_forms_db
    environment:
      POSTGRES_DB: billsons_forms
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: change-me
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

Start services:

```bash
docker compose up -d
```

Run migrations:

```bash
docker compose exec app alembic upgrade head
```

Create the first administrator:

```bash
docker compose exec app python -m app.scripts.create_admin
```

---

## Development Installation

Clone the repository:

```bash
git clone https://github.com/DylanBillson/billsons-forms.git
cd billsons-forms
```

Create your environment file:

```bash
cp .env.example .env
```

Start services:

```bash
docker compose up -d
```

Apply migrations:

```bash
docker compose exec app alembic upgrade head
```

Create an administrator:

```bash
docker compose exec app python -m app.scripts.create_admin
```

---

## Example Form

HTML:

```html
<form method="post" action="https://forms.example.com/api/v1/forms/contact">

    <input type="text" name="name">

    <input type="email" name="email">

    <textarea name="message"></textarea>

    <button type="submit">
        Send
    </button>

</form>
```

---

## API

### Submit Form

```http
POST /api/v1/forms/{slug}
```

Example:

```http
POST /api/v1/forms/contact-us
```

Supported content types:

```text
application/x-www-form-urlencoded
```

```text
multipart/form-data
```

---

## Reverse Proxy Support

Billson's Forms is designed to run behind reverse proxies including:

* Traefik
* Nginx Proxy Manager
* Nginx
* Caddy

HTTPS termination should normally be handled by the reverse proxy.

---

## Development

### Generate a Migration

```bash
docker compose exec app alembic revision --autogenerate -m "description"
```

### Apply Migrations

```bash
docker compose exec app alembic upgrade head
```

### View Logs

```bash
docker compose logs -f app
```

### Access PostgreSQL

```bash
docker compose exec db psql -U postgres
```

---

## Current Functionality

Current v1 functionality includes:

* Authentication
* Session management
* Endpoint management
* Email delivery
* User management
* Audit logging
* Administrative interface
* SMTP credential encryption
* Delivery metadata logging

---

## Philosophy

Billson's Forms follows several core principles:

* Self-host first
* Minimal dependencies
* Privacy conscious
* Operational transparency
* Simple deployment
* Human-readable configuration
* Full ownership of data

The project aims to provide a lightweight alternative to hosted form platforms while remaining easy to deploy, audit, and maintain.

---

## Part of the Billson Stack

Billson's Forms is one of several self-hosted applications developed as part of the Billson Stack project.

The Billson Stack focuses on practical, self-hosted software that is simple to deploy, easy to maintain, and built around long-term operational ownership.

---

## License

Licensed under the Apache License 2.0.

See the LICENSE file for details.
