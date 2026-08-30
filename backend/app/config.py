from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TIGOND_", env_file=".env", extra="ignore")

    credential_key: str = ""
    allowed_origins: str = "http://localhost:3000,http://localhost:4173"
    query_timeout_seconds: int = 15
    profile_sample_rows: int = 10_000
    metadata_database_url: str = "postgresql://tigond_meta:tigond_meta@localhost:55432/tigond_metadata"
    vault_url: str = "http://localhost:8200"
    vault_token: str = "tigond-dev-root"
    vault_mount: str = "tigond"
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "tigond"
    keycloak_client_id: str = "tigond-ui"
    auth_disabled: bool = False
    nifi_url: str = "http://localhost:18080/nifi-api"
    nifi_username: str = ""
    nifi_password: str = ""
    nifi_verify_ssl: bool = False
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_enabled: bool = False

    @property
    def origins(self) -> list[str]:
        return [value.strip() for value in self.allowed_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
