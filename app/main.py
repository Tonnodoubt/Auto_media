from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
from app.core.database import init_db
from app.routers import projects, pipeline, tts, image, video, story, character


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    Path("media/audio").mkdir(parents=True, exist_ok=True)
    Path("media/images").mkdir(parents=True, exist_ok=True)
    Path("media/videos").mkdir(parents=True, exist_ok=True)
    Path("media/characters").mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="AutoMedia API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(pipeline.router)
app.include_router(tts.router)
app.include_router(image.router)
app.include_router(video.router)
app.include_router(story.router)
app.include_router(character.router)

app.mount("/media", StaticFiles(directory="media"), name="media")


@app.get("/")
async def index():
    """API 根路径 - 前端请访问 http://localhost:5173"""
    return JSONResponse({
        "message": "AutoMedia API",
        "version": "0.1.0",
        "frontend": "http://localhost:5173",
        "docs": "/docs"
    })


@app.get("/health")
async def health():
    return {"status": "ok"}
