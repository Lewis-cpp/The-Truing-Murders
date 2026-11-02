from pathlib import Path

from pydantic import PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: PostgresDsn
    # Write requests must come from one of these exact browser origins.
    allowed_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ]
    # Browsers treat http://localhost and http://127.0.0.1 as secure, so Secure stays on.
    cookie_secure: bool = True

    # Model generation (v0.4 spec section 2). Disabled by default: the fixed replies
    # are used and the app behaves exactly like v0.3.
    llm_enabled: bool = False
    llm_enabled_npcs: list[str] = ["NPC01", "NPC02", "NPC03", "NPC04"]
    llm_provider: str = "openai-compatible"
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout_seconds: float = 30.0
    llm_max_input_tokens: int = 4000
    llm_max_output_tokens: int = 400
    llm_session_call_limit: int = 60
    llm_session_token_limit: int = 200000
    llm_concurrency: int = 4

    @model_validator(mode="after")
    def _require_full_config_when_enabled(self):
        if self.llm_enabled and not (self.llm_base_url and self.llm_model and self.llm_api_key):
            raise ValueError(
                "LLM_ENABLED=true requires LLM_BASE_URL, LLM_MODEL and LLM_API_KEY; "
                "refusing to start with a half-configured model gateway"
            )
        return self
