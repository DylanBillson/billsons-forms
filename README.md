# Billson's Forms

Billson's Forms is a self-hosted form backend and management platform for websites.

It allows administrators to create form endpoints through a web interface, configure email delivery settings, manage users, audit activity, and receive website form submissions without relying on third-party services.

Designed as part of the Billson Stack, Billson's Forms prioritises simplicity, self-hosting, auditability, and deployment flexibility.

---

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

Example endpoint:

```
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
* User management actions

Audit logs provide accountability and operational visibility.

---

### Security

Billson's Forms includes:

* Password hashing using Argon2
* Secure session management
* Encrypted SMTP credentials
* Encrypted CAP credentials
* Origin restrictions
* Audit logging
* Soft deletion support

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

---

## Installation

### Clone Repository

```bash
git clone https://github.com/DylanBillson/billsons-forms.git
cd billsons-forms
```

### Create Environment File

```bash
cp .env.example .env
```

Edit the environment file to suit your deployment.

---

### Start Services

```bash
docker compose up -d
```

---

### Run Database Migrations

```bash
docker compose exec app alembic upgrade head
```

---

### Create Initial Administrator

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

Form data is accepted as:

```
application/x-www-form-urlencoded
```

and

```
multipart/form-data
```

depending on implementation.

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

### Run Migrations

```bash
docker compose exec app alembic revision --autogenerate -m "description"
```

```bash
docker compose exec app alembic upgrade head
```

---

### View Logs

```bash
docker compose logs -f app
```

---

### Access Database

```bash
docker compose exec db psql -U postgres
```

---

## Project Status

Billson's Forms is under active development.

Current functionality includes:

* Authentication
* Session management
* Endpoint management
* Email delivery
* User management
* Audit logging
* Administrative interface

Additional features may be added in future releases.

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

The project aims to provide a lightweight alternative to hosted form platforms while remaining easy to deploy and manage.

---

## License

Licensed under the Apache License 2.0.

See the LICENSE file for details.
