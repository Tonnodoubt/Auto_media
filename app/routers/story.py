import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.story import AnalyzeIdeaRequest, GenerateOutlineRequest, GenerateScriptRequest, ChatRequest, RefineRequest, WorldBuildingStartRequest, WorldBuildingTurnRequest
from app.services.story_llm import analyze_idea, generate_outline, generate_script, chat, refine, world_building_start, world_building_turn
from app.services import story_repository as repo
from app.core.api_keys import llm_config_dep

router = APIRouter(prefix="/api/v1/story", tags=["story"])


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
async def api_generate_script(req: GenerateScriptRequest, llm: dict = Depends(llm_config_dep), db: AsyncSession = Depends(get_db)):
    async def event_stream():
        scenes = []
        try:
            async for scene in generate_script(req.story_id, db=db, **llm):
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
    for ep in scenes:
        lines.append(f"# 第{ep['episode']}集 {ep['title']}")
        for s in ep.get("scenes", []):
            lines.append(f"\n## 场景{s['scene_number']}")
            lines.append(f"【环境】{s['environment']}")
            lines.append(f"【画面】{s['visual']}")
            for a in s.get("audio", []):
                lines.append(f"【{a['character']}】{a['line']}")

    script_text = "\n".join(lines)
    return {"story_id": story_id, "script": script_text}
