"""
统一 API Key 提取与校验模块

优先级（以 LLM 为例）：
  前端 X-LLM-API-Key header → .env ANTHROPIC_API_KEY → 400 错误

使用方式：
  keys = extract_api_keys(request)
  image_key = resolve_image_key(keys.image_api_key)
"""
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from app.core.config import settings as _cfg


@dataclass
class ApiKeyBundle:
    llm_api_key: str
    llm_base_url: str
    llm_provider: str
    llm_model: str
    image_api_key: str
    image_base_url: str
    video_api_key: str
    video_base_url: str
    video_provider: str


def extract_api_keys(request: Request) -> ApiKeyBundle:
    """从 HTTP Headers 统一提取所有 API Key 和 Base URL。"""
    return ApiKeyBundle(
        llm_api_key=request.headers.get("X-LLM-API-Key", ""),
        llm_base_url=request.headers.get("X-LLM-Base-URL", ""),
        llm_provider=request.headers.get("X-LLM-Provider", ""),
        llm_model=request.headers.get("X-LLM-Model", ""),
        image_api_key=request.headers.get("X-Image-API-Key", ""),
        image_base_url=request.headers.get("X-Image-Base-URL", ""),
        video_api_key=request.headers.get("X-Video-API-Key", ""),
        video_base_url=request.headers.get("X-Video-Base-URL", ""),
        video_provider=request.headers.get("X-Video-Provider", ""),
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


def validate_user_base_url(url: str) -> str:
    """
    验证用户提供的 base URL，防止 SSRF 攻击。

    规则（始终执行）：
    - 空字符串直接放行（调用方回退到默认值）
    - 必须使用 https 协议
    - 若 hostname 本身是 IP 字面量，拒绝 loopback / 私有 / link-local

    规则（仅 VALIDATE_BASE_URL_DNS=true 时执行）：
    - 对域名做 DNS 解析，拒绝解析结果为内网 IP 的地址
    - 生产环境建议开启；国内开发环境可保持默认 false（境外域名可能无法解析）

    不做 host 白名单：本项目支持任意第三方 API 供应商。
    """
    if not url:
        return url

    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise HTTPException(status_code=400, detail="base_url 必须使用 https 协议")

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="base_url 缺少有效的主机名")

    # 始终检查：hostname 本身是 IP 字面量时拒绝内网地址
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_loopback or ip.is_private or ip.is_link_local:
            raise HTTPException(status_code=400, detail="base_url 不允许指向内网或本地地址")
        return url  # 合法公网 IP，无需再做 DNS 解析
    except ValueError:
        pass  # 普通域名，继续走 DNS 检查逻辑

    # 可选检查：DNS 解析后验证结果 IP
    if _cfg.validate_base_url_dns:
        try:
            infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            raise HTTPException(status_code=400, detail=f"base_url 主机名无法解析: {hostname}")
        for info in infos:
            ip_str = info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if ip.is_loopback or ip.is_private or ip.is_link_local:
                raise HTTPException(status_code=400, detail="base_url 不允许指向内网或本地地址")

    return url


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

# provider 名称 → (api_key 字段名, base_url 字段名)
# "claude" 对应 config 里的 anthropic_* 字段
_PROVIDER_CONFIG: dict[str, tuple[str, str]] = {
    "claude": ("anthropic_api_key", "anthropic_base_url"),
    "openai": ("openai_api_key",    "openai_base_url"),
    "qwen":   ("qwen_api_key",      "qwen_base_url"),
    "zhipu":  ("zhipu_api_key",     "zhipu_base_url"),
    "gemini":      ("gemini_api_key",      "gemini_base_url"),
    "siliconflow": ("siliconflow_api_key", "siliconflow_base_url"),
}


def resolve_llm_config(header_key: str, header_base_url: str, header_provider: str, header_model: str = "") -> dict:
    """
    解析 LLM 配置，优先级：
      api_key  : Header X-LLM-API-Key  → .env <provider>_API_KEY
      base_url : Header X-LLM-Base-URL → .env <provider>_BASE_URL
      provider : Header X-LLM-Provider → settings.default_llm_provider
      model    : Header X-LLM-Model    → "" (后端用 MODEL_MAP 默认值)

    安全规则：
      - 若客户端提供 base_url，则必须同时提供 api_key，不使用服务端 key。
      - 未知/自定义 provider 必须同时提供 api_key 和 base_url，不回退 anthropic 凭证。
    """
    provider = header_provider or _cfg.default_llm_provider
    validated_base_url = validate_user_base_url(header_base_url)

    if provider not in _PROVIDER_CONFIG:
        # 未知/自定义服务商：必须客户端自行提供全部凭证
        if not header_key or not validated_base_url:
            raise HTTPException(
                status_code=400,
                detail=f"自定义服务商 '{provider}' 必须同时提供 X-LLM-API-Key 和 X-LLM-Base-URL",
            )
        return {"api_key": header_key, "base_url": validated_base_url, "provider": provider, "model": header_model}

    key_attr, url_attr = _PROVIDER_CONFIG[provider]

    if validated_base_url:
        # 客户端自定义 base_url：必须同时提供 key，禁止回退服务端凭证
        if not header_key:
            raise HTTPException(
                status_code=400,
                detail="使用自定义 X-LLM-Base-URL 时必须同时提供 X-LLM-API-Key",
            )
        return {"api_key": header_key, "base_url": validated_base_url, "provider": provider, "model": header_model}

    # 未提供自定义 base_url：正常回退到服务端配置
    api_key = header_key or getattr(_cfg, key_attr, "")
    base_url = getattr(_cfg, url_attr, "")
    return {"api_key": api_key, "base_url": base_url, "provider": provider, "model": header_model}


def image_key_dep(request: Request) -> str:
    """Depends：提取并 resolve 图片生成 Key（Header → .env → HTTP 400）"""
    return resolve_image_key(extract_api_keys(request).image_api_key)


def image_config_dep(request: Request) -> dict:
    """Depends：提取图片生成配置（api_key / base_url），返回 dict 供 ** 解构。"""
    keys = extract_api_keys(request)
    validated_base_url = validate_user_base_url(keys.image_base_url)
    if validated_base_url:
        if not keys.image_api_key:
            raise HTTPException(
                status_code=400,
                detail="使用自定义 X-Image-Base-URL 时必须同时提供 X-Image-API-Key",
            )
        return {"image_api_key": keys.image_api_key, "image_base_url": validated_base_url}
    return {
        "image_api_key": resolve_image_key(keys.image_api_key),
        "image_base_url": _cfg.siliconflow_base_url,
    }


def video_key_dep(request: Request) -> str:
    """Depends：提取并 resolve 视频生成 Key（Header → .env → HTTP 400）"""
    return resolve_video_key(extract_api_keys(request).video_api_key)


def video_config_dep(request: Request) -> dict:
    """Depends：提取视频生成配置（api_key / base_url / provider），返回 dict 供 ** 解构。"""
    keys = extract_api_keys(request)
    video_provider = (keys.video_provider or "dashscope").strip().lower()
    if video_provider not in ("dashscope", "kling"):
        raise HTTPException(status_code=400, detail=f"不支持的视频服务商: {video_provider}，可选值: dashscope, kling")
    validated_base_url = validate_user_base_url(keys.video_base_url)

    if validated_base_url:
        if not keys.video_api_key:
            raise HTTPException(
                status_code=400,
                detail="使用自定义 X-Video-Base-URL 时必须同时提供 X-Video-API-Key",
            )
        return {"video_api_key": keys.video_api_key, "video_base_url": validated_base_url, "video_provider": video_provider}

    # Provider-specific .env fallback
    if video_provider == "kling":
        api_key = keys.video_api_key or _cfg.kling_api_key
        base_url = _cfg.kling_base_url
    else:  # dashscope (default)
        api_key = keys.video_api_key or _cfg.dashscope_api_key
        base_url = _cfg.dashscope_base_url

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"视频生成 API Key 未配置 (provider={video_provider})，请在设置页填写或在 .env 中配置对应 Key",
        )
    return {"video_api_key": api_key, "video_base_url": base_url, "video_provider": video_provider}


def llm_config_dep(request: Request) -> dict:
    """Depends：提取 LLM 配置（api_key / base_url / provider），返回 dict 供 ** 解构。"""
    keys = extract_api_keys(request)
    return resolve_llm_config(keys.llm_api_key, keys.llm_base_url, keys.llm_provider, keys.llm_model)
