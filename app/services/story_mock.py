import asyncio
import uuid
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.services import story_repository as repo

MOCK_ANALYZE = {
    "analysis": "世界观有一定基础，但主角动机和核心冲突的视觉表现力不足，需要进一步明确。",
    "suggestions": [
        {
            "label": "超能力/核心设定来源",
            "options": ["非法芯片植入", "神秘包裹辐射", "意识上传错误"]
        },
        {
            "label": "故事核心冲突",
            "options": ["底层反抗财团", "都市异能战斗", "黑色幽默生活流"]
        },
        {
            "label": "情感主线",
            "options": ["热血成长", "爱恨情仇", "兄弟情义"]
        },
    ],
    "placeholder": "或者直接告诉我你的想法，比如：主角叫什么名字？最想看到哪种场景？",
}

MOCK_OUTLINE = {
    "meta": {
        "title": "命运的交汇点",
        "genre": "现代都市",
        "episodes": 6,
        "theme": "在命运的安排下，两个截然不同的人相遇、相知、相爱",
    },
    "characters": [
        {"name": "林晓雨", "role": "女主角", "description": "28岁独立设计师，外表冷静内心细腻，曾经历感情创伤"},
        {"name": "顾北辰", "role": "男主角", "description": "30岁科技公司CEO，工作狂，不善表达情感但内心温柔"},
        {"name": "苏糖", "role": "女配角", "description": "林晓雨的闺蜜，活泼开朗，是两人的红娘"},
    ],
    "relationships": [
        {"source": "林晓雨", "target": "顾北辰", "label": "相爱"},
        {"source": "林晓雨", "target": "苏糖", "label": "闺蜜"},
        {"source": "苏糖", "target": "顾北辰", "label": "撮合"},
    ],
    "outline": [
        {"episode": 1, "title": "意外相遇", "summary": "林晓雨因项目失误闯入顾北辰的发布会，两人第一次相遇充满火花"},
        {"episode": 2, "title": "冤家路窄", "summary": "命运弄人，林晓雨接到的新项目甲方正是顾北辰的公司"},
        {"episode": 3, "title": "渐生情愫", "summary": "合作过程中两人互相了解，顾北辰开始主动接近林晓雨"},
        {"episode": 4, "title": "误会横生", "summary": "前任的出现引发误会，两人关系跌入冰点"},
        {"episode": 5, "title": "真相大白", "summary": "苏糖帮助解开误会，顾北辰向林晓雨坦白心意"},
        {"episode": 6, "title": "幸福终章", "summary": "两人携手面对各自的过去，共同走向新的未来"},
    ],
}

MOCK_SCENES = [
    {
        "episode": 1,
        "title": "意外相遇",
        "scenes": [
            {
                "scene_number": 1,
                "environment": "夜晚，赛博朋克风格的科技发布会现场，蓝紫色霓虹灯光，人群涌动，全息投影屏幕悬浮空中。",
                "visual": "林晓雨手持文件夹，神色慌张地推开会场大门。台上顾北辰正在演讲，两人四目相对，空气瞬间凝固。镜头从顾北辰视角推近林晓雨惊慌的脸。",
                "audio": [
                    {"character": "林晓雨", "line": "不好意思，请问这里是……"},
                    {"character": "顾北辰", "line": "这位女士，你闯入了私人发布会。"},
                    {"character": "林晓雨", "line": "我……我走错了。"},
                ],
            }
        ],
    },
    {
        "episode": 2,
        "title": "冤家路窄",
        "scenes": [
            {
                "scene_number": 1,
                "environment": "白天，现代化设计公司会议室，落地窗透入自然光，白色简约风格。",
                "visual": "林晓雨站在投影屏幕前做提案，PPT 切换到关键页面。会议室门突然打开，顾北辰走进来，两人同时愣住，气氛瞬间凝固。",
                "audio": [
                    {"character": "顾北辰", "line": "林设计师？"},
                    {"character": "林晓雨", "line": "顾总，这次的项目就拜托您了。"},
                ],
            }
        ],
    },
    {
        "episode": 3,
        "title": "渐生情愫",
        "scenes": [
            {
                "scene_number": 1,
                "environment": "傍晚，公司楼顶花园，夕阳将天空染成橙红色，微风吹动植物。",
                "visual": "顾北辰走向独自站在栏杆边的林晓雨，递出一杯咖啡。林晓雨接过，嘴角微微上扬，两人并肩望向城市天际线。",
                "audio": [
                    {"character": "顾北辰", "line": "你今天加班很辛苦。"},
                    {"character": "林晓雨", "line": "没想到顾总也会关心员工。"},
                    {"character": "顾北辰", "line": "只是……特别的员工。"},
                ],
            }
        ],
    },
    {
        "episode": 4,
        "title": "误会横生",
        "scenes": [
            {
                "scene_number": 1,
                "environment": "夜晚，高档餐厅包间，暖黄色烛光，玫瑰花装饰。",
                "visual": "林晓雨站在包间门口，看到顾北辰与一名女子亲密交谈，眼眶泛红。她缓缓转身离开。顾北辰追出来，只看到她消失在走廊尽头的背影。",
                "audio": [
                    {"character": "顾北辰", "line": "林晓雨！"},
                    {"character": "旁白", "line": "有些误会，在开口之前，已经造成了无法挽回的距离。"},
                ],
            }
        ],
    },
    {
        "episode": 5,
        "title": "真相大白",
        "scenes": [
            {
                "scene_number": 1,
                "environment": "下午，苏糖家温馨客厅，暖色调，沙发上摆着抱枕。",
                "visual": "苏糖拉着林晓雨坐在沙发上，认真解释。林晓雨愣住，眼中闪过悔意。此时门铃响起，顾北辰出现在门口，手捧一束白玫瑰，眼神坚定。",
                "audio": [
                    {"character": "苏糖", "line": "那个女人是他表姐，你误会了！"},
                    {"character": "林晓雨", "line": "我……"},
                    {"character": "顾北辰", "line": "我喜欢你，林晓雨。从第一次见面就开始了。"},
                ],
            }
        ],
    },
    {
        "episode": 6,
        "title": "幸福终章",
        "scenes": [
            {
                "scene_number": 1,
                "environment": "夜晚，繁华城市街头，万家灯火，远处烟花绽放。",
                "visual": "两人手牵手漫步，林晓雨靠在顾北辰肩上。镜头缓缓拉远，两人身影融入城市灯光之中。",
                "audio": [
                    {"character": "林晓雨", "line": "以后不许再让我误会了。"},
                    {"character": "顾北辰", "line": "好，我会一直在你身边。"},
                    {"character": "旁白", "line": "命运兜兜转转，终究把对的人送到了一起。"},
                ],
            }
        ],
    },
]


async def mock_analyze_idea(idea: str, genre: str, tone: str, db: AsyncSession = None) -> dict:
    await asyncio.sleep(0.5)
    story_id = str(uuid.uuid4())
    if db:
        await repo.save_story(db, story_id, {"idea": idea, "genre": genre, "tone": tone})
    return {"story_id": story_id, **MOCK_ANALYZE}


async def mock_generate_outline(story_id: str, selected_setting: str, db: AsyncSession = None) -> dict:
    await asyncio.sleep(0.5)
    if db:
        await repo.save_story(db, story_id, {"selected_setting": selected_setting, "outline": MOCK_OUTLINE["outline"]})
    return {"story_id": story_id, **MOCK_OUTLINE}


async def mock_chat(story_id: str, message: str, db: AsyncSession = None) -> AsyncGenerator[str, None]:
    if db:
        story = await repo.get_story(db, story_id)
    else:
        story = {}
    genre = story.get("genre", "现代")
    tone = story.get("tone", "热血")
    reply = f"根据你的想法「{message}」，结合{genre}风格和{tone}基调，建议将故事设定为：{message}，并加入情感冲突与成长弧线，使故事更具张力。"
    for char in reply:
        await asyncio.sleep(0.04)
        yield char


async def mock_generate_script(story_id: str) -> AsyncGenerator[dict, None]:
    for scene in MOCK_SCENES:
        await asyncio.sleep(0.3)
        yield scene


MOCK_WB_QUESTIONS = [
    {"dimension": "时代背景", "text": "故事发生在什么时代背景下？", "options": ["现代都市", "古代架空王朝", "近未来赛博世界"]},
    {"dimension": "主角处境", "text": "主角目前处于什么处境？", "options": ["身处权贵却身不由己", "落魄底层正在崛起", "隐藏身份卧薪尝胆"]},
    {"dimension": "权力结构", "text": "这个世界的权力格局是怎样的？", "options": ["财阀垄断一切资源", "皇权与世家相互制衡", "多方势力混战割据"]},
    {"dimension": "核心冲突", "text": "故事的核心冲突是什么？", "options": ["身份揭穿引发的危机", "复仇与救赎的对抗", "禁忌之恋与家族压力"]},
    {"dimension": "主要人物", "text": "主要人物阵容是怎样的？", "options": ["一主一配，双强对决", "三角关系，情感纠葛", "群像叙事，多线并行"]},
    {"dimension": "情感基调", "text": "整体情感基调偏向哪种风格？", "options": ["先虐后甜，虐心催泪", "热血爽文，燃系逆袭", "甜宠为主，轻松治愈"]},
]


async def mock_world_building_start(idea: str, db: AsyncSession = None) -> dict:
    await asyncio.sleep(0.3)
    story_id = str(uuid.uuid4())
    q = MOCK_WB_QUESTIONS[0]
    question = {"type": "options", "text": q["text"], "options": q["options"], "dimension": q["dimension"]}
    history = [
        {"role": "user", "content": f"种子想法：{idea}，请提出第一个世界观问题"},
        {"role": "assistant", "content": f'{{"status":"questioning","question":{{"type":"options","text":"{q["text"]}","options":{q["options"]},"dimension":"{q["dimension"]}"}},"world_summary":null}}'},
    ]
    if db:
        await repo.save_story(db, story_id, {"idea": idea, "wb_history": history, "wb_turn": 1})
    return {"story_id": story_id, "status": "questioning", "turn": 1, "question": question, "world_summary": None, "usage": None}


async def mock_world_building_turn(story_id: str, answer: str, db: AsyncSession = None) -> dict:
    await asyncio.sleep(0.3)
    if db:
        story = await repo.get_story(db, story_id)
    else:
        story = {}
    turn = story.get("wb_turn", 1)
    new_turn = turn + 1

    if turn >= 6:
        world_summary = f"一个充满张力的短剧世界：{story.get('idea', '')}。世界观完整，人物鲜明，冲突激烈，情感基调深沉热血。"
        if db:
            await repo.save_story(db, story_id, {"wb_turn": new_turn, "selected_setting": world_summary})
        return {"story_id": story_id, "status": "complete", "turn": new_turn, "question": None, "world_summary": world_summary, "usage": None}

    q = MOCK_WB_QUESTIONS[turn]  # turn 从1开始，对应下一个问题
    question = {"type": "options", "text": q["text"], "options": q["options"], "dimension": q["dimension"]}
    if db:
        await repo.save_story(db, story_id, {"wb_turn": new_turn})
    return {"story_id": story_id, "status": "questioning", "turn": new_turn, "question": question, "world_summary": None, "usage": None}
