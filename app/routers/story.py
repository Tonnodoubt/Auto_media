import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.story import AnalyzeIdeaRequest, GenerateOutlineRequest, GenerateScriptRequest, ChatRequest, RefineRequest, WorldBuildingStartRequest, WorldBuildingTurnRequest, PatchStoryRequest, ApplyChatRequest
from app.services.story_llm import analyze_idea, generate_outline, generate_script, chat, refine, world_building_start, world_building_turn, apply_chat
from app.services import story_repository as repo
from app.core.api_keys import llm_config_dep, resolve_llm_config

router = APIRouter(prefix="/api/v1/story", tags=["story"])


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
            async for chunk in chat(req.story_id, req.message, db=db, **llm):
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

    async def event_stream():
        scenes = []
        try:
            async for scene in generate_script(req.story_id, db=db, **script_llm):
                if "__usage__" not in scene:
                    scenes.append(scene)
                    yield f"data: {json.dumps(scene, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps(scene, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
        await repo.save_story(db, req.story_id, {"scenes": scenes})
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/refine")
async def api_refine(req: RefineRequest, llm: dict = Depends(llm_config_dep), db: AsyncSession = Depends(get_db)):
    return await refine(req.story_id, req.change_type, req.change_summary, db=db, **llm)


@router.post("/patch")
async def api_patch(req: PatchStoryRequest, db: AsyncSession = Depends(get_db)):
    fields = {}
    if req.characters is not None:
        fields["characters"] = req.characters
    if req.outline is not None:
        fields["outline"] = req.outline
    if fields:
        await repo.save_story(db, req.story_id, fields)
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
    scenes = story.get("scenes", [])
    if not scenes:
        raise HTTPException(status_code=404, detail="剧本尚未生成，请先调用 generate-script")

    lines = []

    # 注入角色信息
    characters = story.get("characters", [])
    character_images = story.get("character_images", {})
    if characters:
        lines.append("# 角色信息")
        for c in characters:
            name = c.get("name", "")
            role = c.get("role", "")
            desc = c.get("description", "")
            lines.append(f"- {name}（{role}）：{desc}")
            portrait = character_images.get(name, {}).get("portrait_prompt", "") if isinstance(character_images, dict) else ""
            if portrait:
                lines.append(f"  外观提示词: {portrait}")
        lines.append("")

    for ep in scenes:
        lines.append(f"# 第{ep['episode']}集 {ep['title']}")
        for s in ep.get("scenes", []):
            lines.append(f"\n## 场景{s['scene_number']}")
            lines.append(f"【环境】{s['environment']}")
            lighting = s.get("lighting")
            if lighting:
                lines.append(f"【光线】{lighting}")
            mood = s.get("mood")
            if mood:
                lines.append(f"【氛围】{mood}")
            lines.append(f"【画面】{s['visual']}")
            key_actions = s.get("key_actions")
            if key_actions:
                lines.append("【动作拆解】")
                for action in key_actions:
                    lines.append(f"- {action}")
            shot_suggestions = s.get("shot_suggestions")
            if shot_suggestions:
                lines.append("【镜头建议】")
                for suggestion in shot_suggestions:
                    lines.append(f"- {suggestion}")
            transition = s.get("transition_from_previous")
            if transition:
                lines.append(f"【过渡】{transition}")
            for a in s.get("audio", []):
                lines.append(f"【{a['character']}】{a['line']}")

    script_text = "\n".join(lines)
    return {"story_id": story_id, "script": script_text}
