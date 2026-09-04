import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import auth
from app.config import Settings, get_settings
from app.main import app, get_repository
from tests.test_api import FakeRepository

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SETTINGS = Settings(auth_disabled=False, keycloak_url="http://keycloak:8080", keycloak_realm="tigond")
ISSUER = f"{SETTINGS.keycloak_url}/realms/{SETTINGS.keycloak_realm}"


class FakeSigningKey:
    key = PRIVATE_KEY.public_key()


class FakeJWKSClient:
    def get_signing_key_from_jwt(self, _token):
        return FakeSigningKey()


def token(key=PRIVATE_KEY, **overrides) -> str:
    claims = {
        "iss": ISSUER,
        "aud": "tigond-ui",
        "azp": "tigond-ui",
        "sub": "user-1",
        "preferred_username": "ahmed",
        "exp": int(time.time()) + 300,
        "realm_access": {"roles": ["developer"]},
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture(autouse=True)
def keycloak(monkeypatch):
    monkeypatch.setattr(auth, "jwks_client", lambda _url: FakeJWKSClient())
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_repository] = lambda: FakeRepository()
    yield
    app.dependency_overrides.clear()


def get(bearer: str | None):
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    return TestClient(app).get("/api/v1/me", headers=headers)


def test_realm_token_is_accepted_with_roles():
    response = get(token())
    assert response.status_code == 200
    assert response.json() == {"username": "ahmed", "roles": ["developer"]}


def test_missing_token_is_rejected():
    assert get(None).status_code == 401


def test_token_signed_by_another_key_is_rejected():
    assert get(token(key=OTHER_KEY)).status_code == 401


def test_expired_token_is_rejected():
    assert get(token(exp=int(time.time()) - 10)).status_code == 401


def test_token_from_another_issuer_is_rejected():
    assert get(token(iss="http://evil:8080/realms/tigond")).status_code == 401


def test_token_without_api_audience_is_rejected():
    assert get(token(aud="account")).status_code == 401


def test_token_issued_to_another_client_is_rejected():
    assert get(token(azp="other-app")).status_code == 401


def test_role_is_enforced_per_endpoint():
    quality_only = token(realm_access={"roles": ["quality"]})
    forbidden = TestClient(app).get("/api/v1/audit", headers={"Authorization": f"Bearer {quality_only}"})
    assert forbidden.status_code == 403
