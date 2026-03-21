from sqlalchemy import Column, String, Text, Integer, JSON, DateTime, Enum as SAEnum
from sqlalchemy.sql import func
from app.core.database import Base
from app.schemas.pipeline import PipelineStatus


class Story(Base):
    """剧本数据模型"""
    __tablename__ = "stories"

    id = Column(String, primary_key=True)
    idea = Column(Text, nullable=False)
    genre = Column(Text)
    tone = Column(Text)
    selected_setting = Column(Text)
    meta = Column(JSON)  # dict
    characters = Column(JSON)  # List[Character]
    relationships = Column(JSON)  # List[Relationship]
    outline = Column(JSON)  # List[OutlineScene]
    scenes = Column(JSON)  # List[SceneScript]
    wb_history = Column(JSON)  # List[dict] - world building history
    wb_turn = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Pipeline(Base):
    """视频生成流水线模型"""
    __tablename__ = "pipelines"

    id = Column(String, primary_key=True)
    story_id = Column(String, nullable=False, index=True)
    status = Column(SAEnum(PipelineStatus), default=PipelineStatus.PENDING, index=True)
    progress = Column(Integer, default=0)
    current_step = Column(Text)
    error = Column(Text)
    progress_detail = Column(JSON)  # PipelineProgress
    generated_files = Column(JSON)  # dict with file URLs
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
