from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "intelligent-banking-agent"
    api_prefix: str = "/v1"
    hitl_pix_threshold: float = Field(default=5000.0, ge=0)
    default_user_role: str = "customer"
    checkpoint_store_path: str = ".runtime/checkpoints.json"


settings = Settings()
