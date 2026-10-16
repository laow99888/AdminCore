import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, transaction
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from config import db_router
from config.database import load_databases
from apps.core.db_routing_middleware import DatabaseRoutingMiddleware


def _environment():
    return {
        "DB_ENGINE": "django.db.backends.postgresql",
        "DB_NAME": "primary",
        "DB_USER": "app",
        "DB_PASSWORD": "secret",
        "DB_HOST": "primary.internal",
        "DB_PORT": "5432",
        "ADMINCORE_DB_READ_REPLICA_ENABLED": "true",
        "DB_REPLICA_ENGINE": "django.db.backends.postgresql",
        "DB_REPLICA_NAME": "replica",
        "DB_REPLICA_USER": "readonly",
        "DB_REPLICA_PASSWORD": "secret2",
        "DB_REPLICA_HOST": "replica.internal",
        "DB_REPLICA_PORT": "5432",
    }


def test_replica_requires_explicit_independent_connection():
    env = _environment()
    env.pop("DB_REPLICA_HOST")
    with pytest.raises(ImproperlyConfigured, match="DB_REPLICA_HOST"):
        load_databases(env)

    env = _environment()
    env["DB_REPLICA_HOST"] = env["DB_HOST"]
    env["DB_REPLICA_NAME"] = env["DB_NAME"]
    env["DB_REPLICA_USER"] = env["DB_USER"]
    with pytest.raises(ImproperlyConfigured, match="独立"):
        load_databases(env)


def test_router_splits_safe_reads_and_keeps_writes_on_primary(monkeypatch):
    router = db_router.PrimaryReplicaRouter()
    monkeypatch.setattr(db_router, "enabled", lambda: True)
    token = db_router.start_request("GET", False)
    try:
        assert router.db_for_read(object) == "replica"
        assert db_router.current_state()["replica_used"] is True
        assert router.db_for_write(object) == "default"
        assert db_router.current_state()["force_primary"] is True
        assert router.db_for_read(object) == "default"
    finally:
        db_router.finish_request(token)


@pytest.mark.django_db(transaction=True)
def test_transaction_always_reads_primary(monkeypatch):
    router = db_router.PrimaryReplicaRouter()
    monkeypatch.setattr(db_router, "enabled", lambda: True)
    token = db_router.start_request("GET", False)
    try:
        with transaction.atomic():
            assert router.db_for_read(object) == "default"
    finally:
        db_router.finish_request(token)


@override_settings(ADMINCORE_DB_READ_REPLICA_ENABLED=True,
                   ADMINCORE_DB_PRIMARY_STICKY_SECONDS=30)
def test_successful_write_sets_signed_sticky_cookie(monkeypatch):
    monkeypatch.setattr(db_router, "enabled", lambda: True)
    request = RequestFactory().post("/api/v1/example/")

    def view(_request):
        db_router.mark_write()
        return HttpResponse(status=201)

    response = DatabaseRoutingMiddleware(view)(request)
    assert response.status_code == 201
    assert db_router.STICKY_COOKIE in response.cookies
    assert db_router.has_valid_sticky_cookie(
        response.cookies[db_router.STICKY_COOKIE].value)


def test_replica_database_error_retries_safe_request_on_primary(monkeypatch):
    monkeypatch.setattr(db_router, "enabled", lambda: True)
    calls = []

    def view(_request):
        calls.append(len(calls))
        if len(calls) == 1:
            db_router.current_state()["replica_used"] = True
            raise DatabaseError("replica unavailable")
        assert db_router.current_state()["force_primary"] is True
        return HttpResponse("ok")

    response = DatabaseRoutingMiddleware(view)(RequestFactory().get("/api/v1/example/"))
    assert response.status_code == 200
    assert response["X-AdminCore-Read-Replica-Fallback"] == "primary"
    assert calls == [0, 1]


def test_unsafe_request_does_not_retry_replica_error(monkeypatch):
    monkeypatch.setattr(db_router, "enabled", lambda: True)

    def view(_request):
        db_router.current_state()["replica_used"] = True
        raise DatabaseError("replica unavailable")

    with pytest.raises(DatabaseError):
        DatabaseRoutingMiddleware(view)(RequestFactory().post("/api/v1/example/"))
