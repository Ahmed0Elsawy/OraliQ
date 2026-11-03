"""
GET /billing/payment-mode: the one flag the checkout uses to decide whether test-card help may be
shown. It must say "live" unless this server really takes test payments, never on a production
deployment, and never carry anything but the flag.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import payment_gateways as gw

SECRETS = {
    "KASHIER_API_KEY": "kashier-api-key-do-not-leak",
    "KASHIER_SECRET_KEY": "kashier-secret-do-not-leak",
    "KASHIER_MERCHANT_ID": "MID-4455-667",
    "STRIPE_SECRET_KEY": "sk_test_do_not_leak",
    "STRIPE_WEBHOOK_SECRET": "whsec_do_not_leak",
}


@pytest.fixture
def client(monkeypatch):
    for k in ("BILLING_SANDBOX", "KASHIER_MODE", "DATABASE_URL", "SPACE_ID"):
        monkeypatch.delenv(k, raising=False)
    return TestClient(app)


def mode(client) -> dict:
    r = client.get("/api/v1/billing/payment-mode")
    assert r.status_code == 200
    return r.json()


def test_simulated_payments_report_sandbox(client, monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("BILLING_SANDBOX", "1")
    assert mode(client) == {"sandbox_mode": True}


def test_kashier_test_mode_reports_sandbox(client, monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("BILLING_SANDBOX", "0")
    monkeypatch.setenv("KASHIER_MODE", "test")
    assert mode(client) == {"sandbox_mode": True}


def test_live_gateway_reports_live(client, monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("BILLING_SANDBOX", "0")
    assert mode(client) == {"sandbox_mode": False}


def test_production_is_never_sandbox_even_with_test_flags(client, monkeypatch):
    """A stray flag on a deployed server must not put test instructions in front of customers."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("BILLING_SANDBOX", "1")
    monkeypatch.setenv("KASHIER_MODE", "test")
    assert mode(client) == {"sandbox_mode": False}


def test_unknown_run_mode_counts_as_live(client, monkeypatch):
    monkeypatch.setenv("BILLING_SANDBOX", "1")
    monkeypatch.setenv("ENV", "staging")
    assert gw.sandbox_mode() is False
    monkeypatch.delenv("ENV")
    assert gw.sandbox_mode() is False


def test_switching_sandbox_off_is_reported_on_the_next_request(client, monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("KASHIER_MODE", "test")
    monkeypatch.setenv("BILLING_SANDBOX", "0")
    assert mode(client)["sandbox_mode"] is True
    monkeypatch.setenv("KASHIER_MODE", "live")
    assert mode(client)["sandbox_mode"] is False


@pytest.mark.parametrize("sandbox", ["1", "0"])
def test_the_response_carries_nothing_but_the_flag(client, monkeypatch, sandbox):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("BILLING_SANDBOX", sandbox)
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)
    r = client.get("/api/v1/billing/payment-mode")
    assert set(r.json()) == {"sandbox_mode"}
    assert isinstance(r.json()["sandbox_mode"], bool)
    for v in SECRETS.values():
        assert v not in r.text


def test_it_is_public_and_not_cached(client, monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    r = client.get("/api/v1/billing/payment-mode")   # no Authorization header
    assert r.status_code == 200
    assert "no-store" in r.headers.get("cache-control", "")
