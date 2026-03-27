from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import story_repository as repo
from app.services.storyboard_state import (
    load_storyboard_generation_state,
    persist_generated_files_to_pipeline,
    persist_storyboard_generation_state,
)
from app.services.tts import generate_tts_batch, VOICES, DEFAULT_VOICE

router = APIRouter(prefix="/api/v1/tts", tags=["tts"])


class TTSRequest(BaseModel):
    shots: List[dict]
    voice: Optional[str] = DEFAULT_VOICE
    story_id: Optional[str] = None
    pipeline_id: Optional[str] = None


class TTSResult(BaseModel):
    shot_id: str
    audio_url: str
    duration_seconds: float


@router.get("/voices")
async def list_voices():
    return [{"id": k, "name": v} for k, v in VOICES.items()]


@router.post("/{project_id}/generate", response_model=List[TTSResult])
async def generate_audio(
    project_id: str,
    body: TTSRequest,
    db: AsyncSession = Depends(get_db),
):
    voice = body.voice or DEFAULT_VOICE
    if voice not in VOICES:
        raise HTTPException(status_code=400, detail=f"Unknown voice: {voice}")
    try:
        results = await generate_tts_batch(body.shots, voice=voice)
        if body.story_id:
            story = await repo.get_story(db, body.story_id)
            if story:
                generation_state = load_storyboard_generation_state(story)
                effective_pipeline_id = str(body.pipeline_id or generation_state.get("pipeline_id", "") or "").strip()
                generated_files = {
                    "tts": {result["shot_id"]: result for result in results},
                }
                await persist_storyboard_generation_state(
                    db,
                    story_id=body.story_id,
                    story=story,
                    shots=body.shots,
                    partial_shots=True,
                    generated_files=generated_files,
                    pipeline_id=effective_pipeline_id,
                    project_id=project_id,
                )
                if effective_pipeline_id:
                    await persist_generated_files_to_pipeline(
                        db,
                        project_id=project_id,
                        pipeline_id=effective_pipeline_id,
                        story_id=body.story_id,
                        generated_files=generated_files,
                    )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS 生成失败: {e}")
    return results
