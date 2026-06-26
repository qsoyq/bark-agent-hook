from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAISettings(BaseSettings):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = "gpt-5.4"
    temperature: float = 0
    model_config = SettingsConfigDict(env_prefix="openai_", extra="ignore", env_file=".env")


class CloudflareSettings(BaseSettings):
    api_token: str | None = None
    model_config = SettingsConfigDict(env_prefix="cloudflare_", extra="ignore", env_file=".env")


class LodySettings(BaseSettings):
    electron_bootstrap: str | None = None
    electron_session_user_id: str | None = None
    session_id: str | None = None
    workspace_session_id: str | None = None
    model_config = SettingsConfigDict(env_prefix="lody_", extra="ignore", env_file=".env")

    def audit_values(self) -> dict[str, str]:
        values = {
            "LODY_ELECTRON_BOOTSTRAP": self.electron_bootstrap,
            "LODY_ELECTRON_SESSION_USER_ID": self.electron_session_user_id,
            "LODY_SESSION_ID": self.session_id,
            "LODY_WORKSPACE_SESSION_ID": self.workspace_session_id,
        }
        return {key: stripped for key, value in values.items() if value is not None and (stripped := value.strip())}

    def template_values(self) -> dict[str, str]:
        return self.audit_values()

    def has_lody_signal(self) -> bool:
        return bool(self.audit_values())
