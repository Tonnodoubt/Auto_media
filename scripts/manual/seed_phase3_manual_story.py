#!/usr/bin/env python3
"""
Seed the fixed Phase 3 manual-acceptance story into the local database.

Usage:
    uv run python scripts/manual/seed_phase3_manual_story.py
    uv run python scripts/manual/seed_phase3_manual_story.py my-story-id
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.database import AsyncSessionLocal, init_db
from app.services import story_repository as repo


DEFAULT_STORY_ID = "manual-acceptance-rainy-teahouse"
FIXTURE_PATH = ROOT / "docs" / "phase3_manual_acceptance_story.json"


async def _seed(story_id: str) -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    await init_db()
    async with AsyncSessionLocal() as session:
        await repo.save_story(session, story_id, payload)
        saved = await repo.get_story(session, story_id)

    print(f"Seeded Phase 3 manual story into database: story_id={story_id}")
    print(f"Characters: {len(saved.get('characters', []))}")
    print(f"Episodes: {len(saved.get('scenes', []))}")
    print(f"Fixture: {FIXTURE_PATH}")


def main() -> None:
    story_id = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].strip() else DEFAULT_STORY_ID
    asyncio.run(_seed(story_id))


if __name__ == "__main__":
    main()
