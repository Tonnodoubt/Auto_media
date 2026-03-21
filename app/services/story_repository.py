"""Story 和 Pipeline 数据库操作抽象层"""
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.dialects.sqlite import insert
from app.models.story import Story, Pipeline
from app.schemas.pipeline import PipelineStatus


# ============ Story Repository ============

async def save_story(db: AsyncSession, story_id: str, data: dict) -> None:
    """
    保存或更新 story 数据（merge 模式）

    类似于 store.save_story，会合并现有数据
    """
    # 获取现有数据
    existing = await get_story(db, story_id)

    # 合并数据
    merged = {**existing, **data, "id": story_id}

    # 使用 SQLite 的 INSERT OR REPLACE
    stmt = insert(Story).values(**merged)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={k: stmt.excluded[k] for k in merged.keys() if k != "id"}
    )

    await db.execute(stmt)
    await db.commit()


async def get_story(db: AsyncSession, story_id: str) -> dict:
    """
    获取 story 数据

    如果不存在，返回空字典（保持与 store.get_story 一致的行为）
    """
    stmt = select(Story).where(Story.id == story_id)
    result = await db.execute(stmt)
    story = result.scalar_one_or_none()

    if not story:
        return {}

    # 将 SQLAlchemy 模型转换为字典
    return {
        "id": story.id,
        "idea": story.idea,
        "genre": story.genre,
        "tone": story.tone,
        "selected_setting": story.selected_setting,
        "meta": story.meta or {},
        "characters": story.characters or [],
        "relationships": story.relationships or [],
        "outline": story.outline or [],
        "scenes": story.scenes or [],
        "wb_history": story.wb_history or [],
        "wb_turn": story.wb_turn or 0,
        "created_at": story.created_at,
        "updated_at": story.updated_at,
    }


async def list_stories(db: AsyncSession, limit: int = 50) -> List[dict]:
    """获取所有 story 列表（按创建时间倒序）"""
    stmt = select(Story).order_by(desc(Story.created_at)).limit(limit)
    result = await db.execute(stmt)
    stories = result.scalars().all()

    return [
        {
            "id": s.id,
            "idea": s.idea,
            "genre": s.genre,
            "tone": s.tone,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }
        for s in stories
    ]


async def delete_story(db: AsyncSession, story_id: str) -> bool:
    """删除 story（如果存在）"""
    stmt = select(Story).where(Story.id == story_id)
    result = await db.execute(stmt)
    story = result.scalar_one_or_none()

    if not story:
        return False

    await db.delete(story)
    await db.commit()
    return True


# ============ Pipeline Repository ============

async def save_pipeline(
    db: AsyncSession,
    pipeline_id: str,
    story_id: str,
    data: dict
) -> None:
    """
    保存或更新 pipeline 数据

    必需参数：
    - pipeline_id: 流水线 ID
    - story_id: 关联的 story ID
    - data: pipeline 状态数据
    """
    # 准备数据
    pipeline_data = {
        "id": pipeline_id,
        "story_id": story_id,
        "status": data.get("status", PipelineStatus.PENDING),
        "progress": data.get("progress", 0),
        "current_step": data.get("current_step"),
        "error": data.get("error"),
        "progress_detail": data.get("progress_detail"),
        "generated_files": data.get("generated_files"),
    }

    # 使用 SQLite 的 INSERT OR REPLACE
    stmt = insert(Pipeline).values(**pipeline_data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={k: stmt.excluded[k] for k in pipeline_data.keys() if k != "id"}
    )

    await db.execute(stmt)
    await db.commit()


async def get_pipeline(db: AsyncSession, pipeline_id: str) -> dict:
    """
    获取 pipeline 数据

    如果不存在，返回空字典
    """
    stmt = select(Pipeline).where(Pipeline.id == pipeline_id)
    result = await db.execute(stmt)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        return {}

    return {
        "id": pipeline.id,
        "story_id": pipeline.story_id,
        "status": pipeline.status,
        "progress": pipeline.progress,
        "current_step": pipeline.current_step,
        "error": pipeline.error,
        "progress_detail": pipeline.progress_detail,
        "generated_files": pipeline.generated_files,
        "created_at": pipeline.created_at,
        "updated_at": pipeline.updated_at,
    }


async def get_pipeline_by_story(db: AsyncSession, story_id: str) -> Optional[dict]:
    """
    获取 story 关联的最新 pipeline

    返回该 story 最新的 pipeline 记录（按创建时间倒序）
    """
    stmt = (
        select(Pipeline)
        .where(Pipeline.story_id == story_id)
        .order_by(desc(Pipeline.created_at))
        .limit(1)
    )
    result = await db.execute(stmt)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        return None

    return await get_pipeline(db, pipeline.id)


async def list_pipelines_by_story(
    db: AsyncSession,
    story_id: str,
    limit: int = 50
) -> List[dict]:
    """获取 story 的所有 pipeline 记录"""
    stmt = (
        select(Pipeline)
        .where(Pipeline.story_id == story_id)
        .order_by(desc(Pipeline.created_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    pipelines = result.scalars().all()

    return [
        {
            "id": p.id,
            "story_id": p.story_id,
            "status": p.status,
            "progress": p.progress,
            "current_step": p.current_step,
            "error": p.error,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
        for p in pipelines
    ]
