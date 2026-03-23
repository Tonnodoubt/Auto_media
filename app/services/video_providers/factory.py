from app.services.video_providers.base import BaseVideoProvider


def get_video_provider(provider: str) -> BaseVideoProvider:
    """
    Return a video provider instance by name.

    Supported providers: dashscope (default), kling, doubao
    """
    name = (provider or "dashscope").lower()

    if name == "kling":
        from app.services.video_providers.kling import KlingVideoProvider
        return KlingVideoProvider()

    if name == "doubao":
        from app.services.video_providers.doubao import DoubaoVideoProvider
        return DoubaoVideoProvider()

    from app.services.video_providers.dashscope import DashScopeVideoProvider
    return DashScopeVideoProvider()
