from __future__ import annotations

import os
import re
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

import app.db.models  # noqa: F401
from app.core.encryption import encrypt_value
from app.db.base import Base
from app.db.models.form_endpoint import FormEndpoint
from app.db.models.form_endpoint_recipient import FormEndpointRecipient
from app.db.session import get_db
from app.main import app
from app.services.delivery_queue import DeliverySnapshot, create_delivery_snapshot


@pytest.fixture
def db_engine(tmp_path) -> Engine:
    engine = create_engine(f"sqlite:///{tmp_path / 'unit.sqlite'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def db_session_factory(db_engine: Engine):
    return sessionmaker(bind=db_engine, expire_on_commit=False)


@pytest.fixture
def db(db_session_factory):
    session = db_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


def csrf_from(response) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def create_endpoint(session: Session, *, slug: str = "contact") -> FormEndpoint:
    item = FormEndpoint(
        name="Contact", slug=slug, owner_user_id=None, is_active=True, is_deleted=False,
        email_subject="Accepted subject", smtp_host="smtp.example.com", smtp_port=587,
        smtp_username="smtp-user", smtp_password=encrypt_value("smtp-secret"), smtp_security="starttls",
        sender_email="forms@example.com", sender_name="Billson Forms", reply_to_field="email",
        cap_enabled=False, max_payload_kb=256, rate_limit_enabled=True,
        rate_limit_requests=30, rate_limit_window_seconds=60,
    )
    session.add(item)
    session.flush()
    session.add(FormEndpointRecipient(endpoint_id=item.id, email="team@example.com", recipient_type="to", is_active=True))
    session.commit()
    return item


@pytest.fixture
def endpoint(db):
    return create_endpoint(db)


@pytest.fixture
def delivery_snapshot() -> DeliverySnapshot:
    return create_delivery_snapshot(
        submitted_fields={"name": "Ada", "email": "ada@example.com", "message": "private form content"},
        recipients=["team@example.com"], sender_email="forms@example.com", sender_name="Billson Forms",
        subject="Accepted subject", smtp_host="smtp.example.com", smtp_port=587,
        smtp_username="smtp-user", smtp_password="smtp-secret", smtp_security="starttls",
        reply_to_email="ada@example.com",
    )


@pytest.fixture
def postgres_url() -> str:
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("PostgreSQL integration test requires TEST_DATABASE_URL")
    parsed = make_url(value)
    if parsed.get_backend_name() != "postgresql" or "test" not in (parsed.database or "").lower():
        pytest.fail("TEST_DATABASE_URL must point to a dedicated PostgreSQL test database")
    return value


@pytest.fixture
def postgres_engine(postgres_url: str) -> Engine:
    engine = create_engine(postgres_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        yield engine
    except Exception as exc:
        pytest.fail(f"PostgreSQL integration database is unavailable: {exc}")
    finally:
        engine.dispose()


@pytest.fixture
def postgres_session_factory(postgres_engine: Engine):
    factory = sessionmaker(bind=postgres_engine, expire_on_commit=False)

    def clean() -> None:
        with factory() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(delete(table))
            session.commit()

    clean()
    try:
        yield factory
    finally:
        clean()


@pytest.fixture
def postgres_db(postgres_session_factory):
    with postgres_session_factory() as session:
        yield session


@pytest.fixture
def endpoint_factory() -> Callable[[Session], FormEndpoint]:
    return create_endpoint
