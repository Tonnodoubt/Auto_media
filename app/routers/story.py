import json
import logging
from copy import deepcopy
from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.core.story_script import serialize_story_to_script
from app.schemas.story import AnalyzeIdeaRequest, GenerateOutlineRequest, GenerateScriptRequest, ChatRequest, RefineRequest, WorldBuildingStartRequest, WorldBuildingTurnRequest, PatchStoryRequest, ApplyChatRequest
from app.services.story_llm import analyze_idea, generate_outline, generate_script, chat, refine, world_building_start, world_building_turn, apply_chat
from app.services import story_repository as repo
from app.core.api_keys import get_art_style, image_config_dep, llm_config_dep, resolve_llm_config
from app.core.model_defaults import resolve_image_model
from app.services.scene_reference import generate_episode_scene_reference
from app.services.story_context_service import prepare_story_context

router = APIRouter(prefix="/api/v1/story", tags=["story"])
logger = logging.getLogger(__name__)


class SceneReferenceGenerateRequest(BaseModel):
    episode: int
    force_regenerate: bool = False
    model: Optional[str] = None


@router.get("/")
async def list_stories(db: AsyncSession = Depends(get_db)):
    """获取所有已保存的剧本列表"""
    stories = await repo.list_stories(db)
    # 补充每个故事的场景数量
    result = []
    for s in stories:
        full = await repo.get_story(db, s["id"])
        scene_count = sum(len(ep.get("scenes", [])) for ep in full.get("scenes", []))
        result.append({
            **s,
            "scene_count": scene_count,
            "has_script": len(full.get("scenes", [])) > 0,
            "has_character_images": bool(full.get("character_images")),
        })
    return result


@router.get("/{story_id}")
async def get_story(story_id: str, db: AsyncSession = Depends(get_db)):
    """获取单个剧本的完整数据，用于恢复前端状态"""
    story = await repo.get_story(db, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="剧本不存在")
    return story


@router.delete("/{story_id}")
async def delete_story(story_id: str, db: AsyncSession = Depends(get_db)):
    """删除剧本"""
    ok = await repo.delete_story(db, story_id)
    if not ok:
        raise HTTPException(status_code=404, detail="剧本不存在")
    return {"ok": True}


@router.post("/analyze-idea")
async def api_analyze_idea(req: AnalyzeIdeaRequest, llm: dict = Depends(llm_config_dep), db: AsyncSession = Depends(get_db)):
    return await analyze_idea(req.idea, req.genre, req.tone, db=db, **llm)


@router.post("/generate-outline")
async def api_generate_outline(req: GenerateOutlineRequest, llm: dict = Depends(llm_config_dep), db: AsyncSession = Depends(get_db)):
    return await generate_outline(req.story_id, req.selected_setting, db=db, **llm)


@router.post("/chat")
async def api_chat(req: ChatRequest, llm: dict = Depends(llm_config_dep), db: AsyncSession = Depends(get_db)):
    async def event_stream():
        try:
            async for chunk in chat(
                req.story_id,
                req.message,
                db=db,
                mode=req.mode or "generic",
                context=req.context,
                **llm,
            ):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/generate-script")
async def api_generate_script(req: GenerateScriptRequest, request: Request, llm: dict = Depends(llm_config_dep), db: AsyncSession = Depends(get_db)):
    s_provider = request.headers.get("X-Script-Provider", "")
    s_api_key  = request.headers.get("X-Script-API-Key",  "")
    s_base_url = request.headers.get("X-Script-Base-URL", "")
    s_model    = request.headers.get("X-Script-Model",    "")

    if s_provider or s_api_key or s_base_url or s_model:
        script_llm = resolve_llm_config(s_api_key, s_base_url, s_provider, s_model)
    else:
        script_llm = llm

    script_api_key = str(script_llm.get("api_key", "")).strip()
    story_record = await repo.get_story(db, req.story_id)
    if not story_record:
        raise HTTPException(status_code=404, detail="故事不存在")
    if not script_api_key and not settings.debug:
        raise HTTPException(
            status_code=400,
            detail="剧本生成 需要可用的 LLM API Key，请在前端设置或后端 .env 中完成配置",
        )
    if script_api_key and not story_record.get("outline", []):
        raise HTTPException(status_code=400, detail="剧本生成失败：当前故事缺少大纲，请先完成世界观与大纲生成")

    async def event_stream():
        scenes = []
        success = False
        try:
            async for scene in generate_script(req.story_id, db=db, **script_llm):
                if "__usage__" not in scene:
                    scenes.append(scene)
                    yield f"data: {json.dumps(scene, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps(scene, ensure_ascii=False)}\n\n"
            success = True
        except Exception as e:
            logger.exception(
                "Generate script failed story_id=%s provider=%s model=%s",
                req.story_id,
                script_llm.get("provider", ""),
                script_llm.get("model", ""),
            )
            yield f"data: [ERROR] {str(e)}\n\n"
        if success:
            await repo.save_story(db, req.story_id, {"scenes": scenes})
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/refine")
async def api_refine(req: RefineRequest, llm: dict = Depends(llm_config_dep), db: AsyncSession = Depends(get_db)):
    return await refine(req.story_id, req.change_type, req.change_summary, db=db, **llm)


@router.post("/patch")
async def api_patch(req: PatchStoryRequest, db: AsyncSession = Depends(get_db)):
    fields = {}
    invalidate_appearance = False
    invalidate_scene_style = False
    invalidate_script = False
    if req.characters is not None:
        fields["characters"] = req.characters
        invalidate_appearance = True
        invalidate_script = True
    if req.outline is not None:
        fields["outline"] = req.outline
        invalidate_scene_style = True
        invalidate_script = True
    if req.art_style is not None:
        fields["art_style"] = req.art_style
    if invalidate_script:
        fields["scenes"] = []
    if fields:
        await repo.save_story(db, req.story_id, fields)
    if invalidate_appearance or invalidate_scene_style:
        await repo.invalidate_story_consistency_cache(
            db,
            req.story_id,
            appearance=invalidate_appearance,
            scene_style=invalidate_scene_style,
        )
    return {"ok": True}


@router.post("/apply-chat")
async def api_apply_chat(req: ApplyChatRequest, llm: dict = Depends(llm_config_dep), db: AsyncSession = Depends(get_db)):
    return await apply_chat(
        req.story_id, req.change_type, req.chat_history, req.current_item, db=db, **llm
    )


@router.post("/world-building/start")
async def api_wb_start(req: WorldBuildingStartRequest, llm: dict = Depends(llm_config_dep), db: AsyncSession = Depends(get_db)):
    return await world_building_start(req.idea, db=db, **llm)


@router.post("/world-building/turn")
async def api_wb_turn(req: WorldBuildingTurnRequest, llm: dict = Depends(llm_config_dep), db: AsyncSession = Depends(get_db)):
    return await world_building_turn(req.story_id, req.answer, db=db, **llm)


@router.post("/{story_id}/finalize")
async def finalize_script(story_id: str, db: AsyncSession = Depends(get_db)):
    """把第一阶段剧本序列化为文本，供第二阶段 pipeline 使用"""
    story = await repo.get_story(db, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="剧本不存在")

    scenes = story.get("scenes", [])
    if not scenes:
        raise HTTPException(status_code=404, detail="剧本尚未生成，请先调用 generate-script")

    script_text = serialize_story_to_script(story)
    return {"story_id": story_id, "script": script_text}


@router.post("/{story_id}/storyboard-script")
async def build_storyboard_script(
    story_id: str,
    body: dict | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
):
    """按选中的场景统一序列化 storyboard 输入文本。"""
    story = await repo.get_story(db, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="剧本不存在")
    if not story.get("scenes", []):
        raise HTTPException(status_code=404, detail="剧本尚未生成，请先调用 generate-script")

    selected_scene_numbers = None
    if isinstance(body, dict):
        raw_selected_scenes = body.get("selected_scenes")
        if isinstance(raw_selected_scenes, dict):
            selected_scene_numbers = raw_selected_scenes

    script_text = serialize_story_to_script(
        story,
        selected_scene_numbers=selected_scene_numbers,
    )
    return {"story_id": story_id, "script": script_text}


@router.post("/{story_id}/scene-reference/generate")
async def generate_scene_reference(
    story_id: str,
    body: SceneReferenceGenerateRequest,
    request: Request,
    llm: dict = Depends(llm_config_dep),
    image_config: dict = Depends(image_config_dep),
    db: AsyncSession = Depends(get_db),
):
    story, story_context = await prepare_story_context(
        db,
        story_id,
        provider=llm["provider"],
        model=llm["model"],
        api_key=llm["api_key"],
        base_url=llm["base_url"],
    )
    if not story:
        raise HTTPException(status_code=404, detail="剧本不存在")

    art_style = get_art_style(request)
    effective_model = resolve_image_model(body.model or "", image_config.get("image_base_url", ""))
    existing_episode_assets = dict((story.get("meta") or {}).get("episode_reference_assets") or {})
    episode_prefix = f"ep{body.episode:02d}_"
    existing_groups = []
    if not body.force_regenerate:
        existing_groups = [
            {
                "environment_pack_key": pack_key,
                "affected_scene_keys": list(asset.get("affected_scene_keys") or []),
                "asset": asset,
            }
            for pack_key, asset in sorted(existing_episode_assets.items())
            if pack_key.startswith(episode_prefix) and asset.get("status") == "ready"
        ]

    try:
        result = await generate_episode_scene_reference(
            story,
            story_context,
            episode=body.episode,
            model=effective_model,
            art_style=art_style,
            existing_assets=[group["asset"] for group in existing_groups],
            **image_config,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Scene reference generation failed story_id=%s episode=%s", story_id, body.episode)
        raise HTTPException(status_code=500, detail=f"环境图生成失败: {exc}") from exc

    latest_story = await repo.get_story(db, story_id)
    meta = dict((latest_story or story).get("meta") or {})
    episode_reference_assets = {
        pack_key: asset
        for pack_key, asset in dict(meta.get("episode_reference_assets") or {}).items()
        if not pack_key.startswith(episode_prefix)
    }
    scene_reference_assets = {
        scene_key: asset
        for scene_key, asset in dict(meta.get("scene_reference_assets") or {}).items()
        if not scene_key.startswith(f"ep{body.episode:02d}_scene")
    }

    for group in result["groups"]:
        episode_reference_assets[group["environment_pack_key"]] = deepcopy(group["asset"])
        for scene_key in group["affected_scene_keys"]:
            scene_reference_assets[scene_key] = deepcopy(group["asset"])

    await repo.save_story(
        db,
        story_id,
        {
            "meta": {
                **meta,
                "episode_reference_assets": episode_reference_assets,
                "scene_reference_assets": scene_reference_assets,
            }
        },
    )
    return result
