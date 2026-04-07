import logging

from pydantic import field_validator
from pydantic_settings import BaseSettings


logger = logging.getLogger(__name__)

DEFAULT_LLM_SLOW_LOG_THRESHOLD_MS = 5000
DEFAULT_OUTLINE_GENERATION_CONCURRENCY = 2
MAX_OUTLINE_GENERATION_CONCURRENCY = 3
#默认并发数
DEFAULT_SCRIPT_GENERATION_CONCURRENCY = 3
#最大并发数
MAX_SCRIPT_GENERATION_CONCURRENCY = 6


class Settings(BaseSettings):
    app_name: str = "AutoMedia API"
    database_url: str = "sqlite+aiosqlite:///./automedia.db"
    debug: bool = True
    #表示是否开启 LLM 调用遥测/监控功能，默认为 True。开启后会记录 LLM 调用的性能数据（如响应时间、错误率等），以便进行分析和优化。关闭后则不收集这些数据，适合开发环境或对性能监控要求不高的场景。
    llm_telemetry_enabled: bool = True
    llm_slow_log_threshold_ms: int = DEFAULT_LLM_SLOW_LOG_THRESHOLD_MS
    outline_generation_concurrency: int = DEFAULT_OUTLINE_GENERATION_CONCURRENCY
    script_generation_concurrency: int = DEFAULT_SCRIPT_GENERATION_CONCURRENCY
    quality_layer_enabled: bool = True
    quality_outline_enabled: bool = True
    quality_storyboard_enabled: bool = True
    quality_character_appearance_enabled: bool = True
    quality_scene_style_enabled: bool = True
    quality_generation_payload_enabled: bool = True
    quality_scene_reference_enabled: bool = True
    quality_character_design_enabled: bool = True
    quality_dspy_enabled: bool = True
    quality_judge_enabled: bool = True
    quality_judge_shadow_mode: bool = True
    quality_feedback_loop_enabled: bool = True
    quality_feedback_max_retries: int = 1
    quality_judge_provider: str = ""
    quality_judge_model: str = ""
    quality_judge_api_key: str = ""
    quality_judge_base_url: str = ""

    # LLM
    default_llm_provider: str = "claude"
    default_image_provider: str = "siliconflow"
    default_video_provider: str = "dashscope"

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
    default_image_model: str = "black-forest-labs/FLUX.1-schnell"
    siliconflow_image_api_key: str = ""
    siliconflow_image_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_image_model: str = "black-forest-labs/FLUX.1-schnell"
    doubao_image_api_key: str = ""
    doubao_image_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_image_model: str = ""

    # Video generation
    default_video_model: str = "wan2.6-i2v-flash"
    dashscope_video_api_key: str = ""
    dashscope_video_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    dashscope_video_model: str = "wan2.6-i2v-flash"

    kling_video_api_key: str = ""
    kling_video_base_url: str = "https://api.klingai.com"
    kling_api_key: str = ""
    kling_base_url: str = "https://api.klingai.com"
    kling_video_model: str = "kling-v2-master"

    minimax_video_api_key: str = ""
    minimax_video_base_url: str = "https://api.minimaxi.chat"
    minimax_video_model: str = "video-01"

    doubao_video_api_key: str = ""
    doubao_video_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_api_key: str = ""
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_video_model: str = ""

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

    @field_validator("default_llm_provider", "default_image_provider", "default_video_provider", mode="before")
    @classmethod
    def _normalize_provider(cls, value):
        return str(value or "").strip().lower()

    @field_validator("llm_slow_log_threshold_ms", mode="before")
    @classmethod
    def _normalize_llm_slow_log_threshold_ms(cls, value):
        try:
            threshold = int(value)
        except (TypeError, ValueError) as exc:
            logger.error("Invalid LLM slow log threshold value=%r; expected an integer", value)
            raise ValueError("llm_slow_log_threshold_ms must be an integer >= 0") from exc

        if threshold < 0:
            logger.warning(
                "Invalid negative llm_slow_log_threshold_ms=%s; falling back to default=%s",
                threshold,
                DEFAULT_LLM_SLOW_LOG_THRESHOLD_MS,
            )
            return DEFAULT_LLM_SLOW_LOG_THRESHOLD_MS

        return threshold

    @field_validator("outline_generation_concurrency", mode="before")
    @classmethod
    def _normalize_outline_generation_concurrency(cls, value):
        try:
            concurrency = int(value)
        except (TypeError, ValueError) as exc:
            logger.error("Invalid outline generation concurrency value=%r; expected an integer", value)
            raise ValueError("outline_generation_concurrency must be an integer between 1 and 3") from exc

        if concurrency < 1:
            logger.warning("Invalid outline_generation_concurrency=%s; falling back to 1", concurrency)
            return 1
        if concurrency > MAX_OUTLINE_GENERATION_CONCURRENCY:
            logger.warning(
                "outline_generation_concurrency=%s exceeds max=%s; falling back to max",
                concurrency,
                MAX_OUTLINE_GENERATION_CONCURRENCY,
            )
            return MAX_OUTLINE_GENERATION_CONCURRENCY

        return concurrency

    @field_validator("quality_feedback_max_retries", mode="before")
    @classmethod
    def _normalize_quality_feedback_max_retries(cls, value):
        try:
            retries = int(value)
        except (TypeError, ValueError) as exc:
            logger.error("Invalid quality feedback retry value=%r; expected an integer", value)
            raise ValueError("quality_feedback_max_retries must be an integer >= 0") from exc

        if retries < 0:
            logger.warning("Invalid negative quality_feedback_max_retries=%s; falling back to 0", retries)
            return 0
        return retries

    @field_validator("script_generation_concurrency", mode="before")
    @classmethod
    def _normalize_script_generation_concurrency(cls, value):
        try:
            concurrency = int(value)
        except (TypeError, ValueError) as exc:
            logger.error("Invalid script generation concurrency value=%r; expected an integer", value)
            raise ValueError("script_generation_concurrency must be an integer between 1 and 6") from exc

        if concurrency < 1:
            logger.warning("Invalid script_generation_concurrency=%s; falling back to 1", concurrency)
            return 1
        if concurrency > MAX_SCRIPT_GENERATION_CONCURRENCY:
            logger.warning(
                "script_generation_concurrency=%s exceeds max=%s; falling back to max",
                concurrency,
                MAX_SCRIPT_GENERATION_CONCURRENCY,
            )
            return MAX_SCRIPT_GENERATION_CONCURRENCY

        return concurrency

    class Config:
        env_file = ".env"


settings = Settings()
