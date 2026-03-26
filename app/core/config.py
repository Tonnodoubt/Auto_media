from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "AutoMedia API"
    database_url: str = "sqlite+aiosqlite:///./automedia.db"
    debug: bool = True

    # LLM
    default_llm_provider: str = "claude"

    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    zhipu_api_key: str = ""
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"

    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    # Image generation
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"

    # Video generation
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1"

    kling_api_key: str = ""
    kling_base_url: str = "https://api.klingai.com"

    doubao_api_key: str = ""
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"

    # Security: whether to DNS-resolve user-supplied base URLs and reject private IPs
    # Set to false in dev environments where foreign domains may not resolve
    validate_base_url_dns: bool = False

    @field_validator("debug", mode="before")
    @classmethod
    def _normalize_debug(cls, value):
        if isinstance(value, bool):
            return value
        normalized = str(value or "").strip().lower()
        if normalized in {"release", "prod", "production", "off"}:
            return False
        if normalized in {"debug", "dev", "development", "on"}:
            return True
        return value

    class Config:
        env_file = ".env"


settings = Settings()
