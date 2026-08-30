from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    username: str
    roles: frozenset[str]


@lru_cache
def jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url)


def current_principal(credentials: HTTPAuthorizationCredentials | None = Security(bearer), settings: Settings = Depends(get_settings)) -> Principal:
    if settings.auth_disabled:
        return Principal("local-developer", frozenset({"administrator", "developer", "operator", "quality", "governance"}))
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    issuer = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
    try:
        signing_key = jwks_client(f"{issuer}/protocol/openid-connect/certs").get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(credentials.credentials, signing_key.key, algorithms=["RS256"], audience=settings.audience, issuer=issuer)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from exc
    if claims.get("azp", settings.keycloak_client_id) != settings.keycloak_client_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token was issued to another client")
    return Principal(claims.get("preferred_username", claims.get("sub", "unknown")), frozenset(claims.get("realm_access", {}).get("roles", [])))


def require_roles(*allowed: str):
    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.roles.intersection(allowed):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return principal
    return dependency
