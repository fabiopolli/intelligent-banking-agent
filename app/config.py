from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "intelligent-banking-agent"
    api_prefix: str = "/v1"
    hitl_pix_threshold: float = Field(default=5000.0, ge=0)
    pix_daily_limit: float = Field(default=50000.0, ge=0)
    default_user_role: str = "customer"
    checkpoint_store_path: str = ".runtime/checkpoints.json"
    llm_grounded_faq_enabled: bool = False
    llm_provider: str = "local"
    llm_model: str = "gpt-5.6-luna"
    llm_timeout_seconds: float = Field(default=20.0, gt=0)
    llm_context_char_limit: int = Field(default=3000, ge=500)
    openai_api_key: str | None = None
    docker_model_runner_base_url: str = "http://localhost:12434/engines/v1"
    docker_model_runner_model: str = "ai/smollm2"
    mcp_server_host: str = "0.0.0.0"
    mcp_server_port: int = Field(default=8600, ge=1, le=65535)
    internal_tool_api_key: str = Field(default="demo-internal-tool-key", min_length=8)


settings = Settings()
