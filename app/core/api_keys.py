"""
统一 API Key 提取与校验模块

优先级（以 LLM 为例）：
  前端 X-LLM-API-Key header → .env ANTHROPIC_API_KEY → 400 错误

使用方式：
  keys = extract_api_keys(request)
  image_key = resolve_image_key(keys.image_api_key)
"""
from dataclasses import dataclass
from fastapi import HTTPException, Request
from app.core.config import settings as _cfg


@dataclass
class ApiKeyBundle:
    llm_api_key: str
    llm_base_url: str
    llm_provider: str
    image_api_key: str
    image_base_url: str
    video_api_key: str
    video_base_url: str


def extract_api_keys(request: Request) -> ApiKeyBundle:
    """从 HTTP Headers 统一提取所有 API Key 和 Base URL。"""
    return ApiKeyBundle(
        llm_api_key=request.headers.get("X-LLM-API-Key", ""),
        llm_base_url=request.headers.get("X-LLM-Base-URL", ""),
        llm_provider=request.headers.get("X-LLM-Provider", ""),
        image_api_key=request.headers.get("X-Image-API-Key", ""),
        image_base_url=request.headers.get("X-Image-Base-URL", ""),
        video_api_key=request.headers.get("X-Video-API-Key", ""),
        video_base_url=request.headers.get("X-Video-Base-URL", ""),
    )


def resolve_image_key(header_key: str) -> str:
    """
    解析图片生成 Key：前端 header → .env SILICONFLOW_API_KEY → 400

    不抛出 ValueError，统一返回 HTTPException 以便 FastAPI 直接响应。
    """
    key = header_key or _cfg.siliconflow_api_key
    if not key:
        raise HTTPException(
            status_code=400,
            detail="图片生成 API Key 未配置，请在设置页填写或在 .env 中配置 SILICONFLOW_API_KEY",
        )
    return key


def resolve_video_key(header_key: str) -> str:
    """
    解析视频生成 Key：前端 header → .env DASHSCOPE_API_KEY → 400
    """
    key = header_key or _cfg.dashscope_api_key
    if not key:
        raise HTTPException(
            status_code=400,
            detail="视频生成 API Key 未配置，请在设置页填写或在 .env 中配置 DASHSCOPE_API_KEY",
        )
    return key


def mask_key(key: str) -> str:
    """脱敏 API Key，用于日志和错误信息输出，避免明文泄露。"""
    if not key:
        return "(empty)"
    if len(key) <= 8:
        return "***"
    return key[:4] + "..." + key[-4:]


# ── FastAPI Depends 依赖函数 ──────────────────────────────────────────────────
# 用于 router 函数签名，消除每个 endpoint 重复的两行 extract + resolve 样板代码。
# FastAPI 自动将 request: Request 注入，HTTPException 在此处抛出与在 endpoint 中等价。

def image_key_dep(request: Request) -> str:
    """Depends：提取并 resolve 图片生成 Key（Header → .env → HTTP 400）"""
    return resolve_image_key(extract_api_keys(request).image_api_key)


def image_config_dep(request: Request) -> dict:
    """Depends：提取图片生成配置（api_key / base_url），返回 dict 供 ** 解构。"""
    keys = extract_api_keys(request)
    return {
        "image_api_key": resolve_image_key(keys.image_api_key),
        "image_base_url": keys.image_base_url or _cfg.siliconflow_base_url,
    }


def video_key_dep(request: Request) -> str:
    """Depends：提取并 resolve 视频生成 Key（Header → .env → HTTP 400）"""
    return resolve_video_key(extract_api_keys(request).video_api_key)


def video_config_dep(request: Request) -> dict:
    """Depends：提取视频生成配置（api_key / base_url），返回 dict 供 ** 解构。"""
    keys = extract_api_keys(request)
    return {
        "video_api_key": resolve_video_key(keys.video_api_key),
        "video_base_url": keys.video_base_url or _cfg.dashscope_base_url,
    }


def llm_config_dep(request: Request) -> dict:
    """Depends：提取 LLM 配置（api_key / base_url / provider），返回 dict 供 ** 解构。"""
    keys = extract_api_keys(request)
    return {
        "api_key": keys.llm_api_key,
        "base_url": keys.llm_base_url,
        "provider": keys.llm_provider,
    }
