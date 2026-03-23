import logging

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=settings.debug)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 为已存在的旧库补充 character_images 列（新库由 create_all 自动建好）
        def _column_missing(sync_conn):
            return "character_images" not in {
                col["name"] for col in inspect(sync_conn).get_columns("stories")
            }
        if await conn.run_sync(_column_missing):
            await conn.execute(text("ALTER TABLE stories ADD COLUMN character_images JSON"))
            logger.info("Migration applied: added character_images column to stories table")
