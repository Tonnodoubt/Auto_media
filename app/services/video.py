import asyncio
import httpx
from pathlib import Path

from app.core.api_keys import mask_key

VIDEO_DIR = Path("media/videos")
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MODEL = "wan2.6-i2v-flash"
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
DASHSCOPE_SUBMIT_PATH = "/services/aigc/image2video/video-synthesis"
DASHSCOPE_TASK_PATH = "/tasks/{task_id}"


async def _submit_task(client: httpx.AsyncClient, image_url: str, prompt: str, model: str, api_key: str, video_base_url: str) -> str:
    """Submit image-to-video task, return task_id."""
    submit_url = f"{video_base_url}{DASHSCOPE_SUBMIT_PATH}"
    resp = await client.post(
        submit_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-DashScope-Async": "enable",
        },
        json={
            "model": model,
            "input": {"image_url": image_url, "prompt": prompt},
            "parameters": {"duration": 5},
        },
    )
    print(f"[VIDEO SUBMIT] status={resp.status_code} key={mask_key(api_key)} base={video_base_url}")
    if not resp.is_success:
        raise RuntimeError(f"视频任务提交 API 错误 {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    task_id = data["output"]["task_id"]
    return task_id


async def _poll_task(client: httpx.AsyncClient, task_id: str, api_key: str, video_base_url: str, timeout: int = 300) -> str:
    """Poll task until succeeded, return video URL."""
    url = f"{video_base_url}{DASHSCOPE_TASK_PATH.format(task_id=task_id)}"
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(5)
        resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        if not resp.is_success:
            raise RuntimeError(f"视频任务查询 API 错误 {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        status = data["output"]["task_status"]
        if status == "SUCCEEDED":
            return data["output"]["video_url"]
        if status in ("FAILED", "CANCELED"):
            raise RuntimeError(f"视频任务失败: {data['output'].get('message', status)}")
    raise TimeoutError(f"视频任务超时: {task_id}")


async def generate_video(image_url: str, prompt: str, shot_id: str, model: str = DEFAULT_MODEL, video_api_key: str = "", video_base_url: str = "") -> dict:
    """Generate video for a single shot. Returns { shot_id, video_path, video_url }."""
    effective_base = video_base_url or DASHSCOPE_BASE_URL
    async with httpx.AsyncClient(timeout=30) as client:
        task_id = await _submit_task(client, image_url, prompt, model, video_api_key, effective_base)

    async with httpx.AsyncClient(timeout=30) as client:
        remote_video_url = await _poll_task(client, task_id, video_api_key, effective_base)

        # Download and save locally
        vid_resp = await client.get(remote_video_url)
        vid_resp.raise_for_status()

    output_path = VIDEO_DIR / f"{shot_id}.mp4"
    output_path.write_bytes(vid_resp.content)

    return {
        "shot_id": shot_id,
        "video_path": str(output_path),
        "video_url": f"/media/videos/{shot_id}.mp4",
    }


async def generate_videos_batch(shots: list[dict], base_url: str, model: str = DEFAULT_MODEL, video_api_key: str = "", video_base_url: str = "") -> list[dict]:
    """
    Generate videos for all shots concurrently.
    Each shot must have: shot_id, image_url (relative), visual_prompt, camera_motion.
    base_url: server base URL to convert relative image_url to absolute.
    video_base_url: video API base URL (defaults to DashScope).
    """
    tasks = [
        generate_video(
            image_url=f"{base_url}{shot['image_url']}",
            prompt=f"{shot['visual_prompt']} {shot['camera_motion']}",
            shot_id=shot["shot_id"],
            model=model,
            video_api_key=video_api_key,
            video_base_url=video_base_url,
        )
        for shot in shots
        if shot.get("image_url")
    ]
    return list(await asyncio.gather(*tasks))
