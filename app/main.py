from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.database import init_db
from app.routers import character, image, pipeline, story, tts, video

BASE_DIR = Path(__file__).resolve().parent.parent
MEDIA_DIR = BASE_DIR / "media"
FRONTEND_DIST_DIR = BASE_DIR / "frontend" / "dist"
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"
FRONTEND_RESERVED_PREFIXES = (
    "api",
    "media",
    "health",
    "docs",
    "redoc",
    "openapi.json",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


def _frontend_build_available() -> bool:
    return FRONTEND_INDEX_FILE.is_file()


def _is_reserved_frontend_path(full_path: str) -> bool:
    normalized = str(full_path or "").strip().lstrip("/")
    if not normalized:
        return False
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}/")
        for prefix in FRONTEND_RESERVED_PREFIXES
    )


def _resolve_frontend_file(full_path: str) -> Path | None:
    if not _frontend_build_available():
        return None

    normalized = str(full_path or "").strip().lstrip("/")
    if not normalized:
        return FRONTEND_INDEX_FILE

    root = FRONTEND_DIST_DIR.resolve(strict=False)
    candidate = (FRONTEND_DIST_DIR / normalized).resolve(strict=False)
    if not candidate.is_relative_to(root):
        return None
    if candidate.is_file():
        return candidate
    if Path(normalized).suffix:
        return None
    return FRONTEND_INDEX_FILE


app = FastAPI(title="AutoMedia API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
        "https://localhost",
        "https://127.0.0.1",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline.router)
app.include_router(tts.router)
app.include_router(image.router)
app.include_router(video.router)
app.include_router(story.router)
app.include_router(character.router)

# Ensure media directories exist before mounting static files
for _d in ("audio", "images", "videos", "characters", "episodes"):
    (MEDIA_DIR / _d).mkdir(parents=True, exist_ok=True)

app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


@app.get("/", include_in_schema=False)
async def index():
    frontend_file = _resolve_frontend_file("")
    if frontend_file:
        return FileResponse(frontend_file)

    return JSONResponse(
        {
            "message": "AutoMedia API",
            "version": "0.1.0",
            "frontend_build": False,
            "frontend_hint": "Build frontend/dist to serve the app from this same origin.",
            "docs": "/docs",
        }
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/{full_path:path}", include_in_schema=False)
async def frontend_fallback(full_path: str):
    if _is_reserved_frontend_path(full_path):
        raise HTTPException(status_code=404, detail="Not Found")

    frontend_file = _resolve_frontend_file(full_path)
    if frontend_file:
        return FileResponse(frontend_file)

    raise HTTPException(status_code=404, detail="Not Found")
