# ruff: noqa: RUF001

import asyncio
import uuid
from typing import AsyncGenerator, Optional
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
        "logline": "独立设计师林晓雨误闯科技发布会后，被迫与高冷 CEO 顾北辰合作，在冲突与误会中一步步确认彼此心意。",
        "visual_tone": "都市情感电影感，冷暖光对比下的高压职场与私密情绪空间。",
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
        {
            "episode": 1,
            "title": "意外相遇",
            "summary": "林晓雨因项目失误闯入顾北辰的发布会，两人第一次相遇充满火花。",
            "beats": ["林晓雨误入高规格发布会现场。", "顾北辰当众拦下她，两人第一次正面碰撞。", "这次尴尬相遇为后续合作埋下伏笔。"],
            "scene_list": ["Scene 1: [夜] [室内] [科技发布会现场] - 林晓雨误闯会场，与台上的顾北辰正面相遇。"],
        },
        {
            "episode": 2,
            "title": "冤家路窄",
            "summary": "命运弄人，林晓雨接到的新项目甲方正是顾北辰的公司。",
            "beats": ["林晓雨在会议室做提案。", "顾北辰突然现身，揭示两人必须合作。", "双方压下情绪，关系被迫进入新的阶段。"],
            "scene_list": ["Scene 1: [白天] [室内] [设计公司会议室] - 提案现场被顾北辰打断，合作关系正式成立。"],
        },
        {
            "episode": 3,
            "title": "渐生情愫",
            "summary": "合作过程中两人互相了解，顾北辰开始主动接近林晓雨。",
            "beats": ["加班后的短暂独处打破职场距离。", "顾北辰主动示好，态度明显不同。", "林晓雨对他的印象开始松动。"],
            "scene_list": ["Scene 1: [傍晚] [室外] [公司楼顶花园] - 顾北辰递上咖啡，与林晓雨共享片刻宁静。"],
        },
        {
            "episode": 4,
            "title": "误会横生",
            "summary": "前任的出现引发误会，两人关系跌入冰点。",
            "beats": ["林晓雨撞见顾北辰与另一名女子亲密交谈。", "她情绪失控后转身离开。", "顾北辰追出时已经错过解释时机。"],
            "scene_list": ["Scene 1: [夜] [室内] [高档餐厅包间] - 林晓雨误会顾北辰，转身离开。"],
        },
        {
            "episode": 5,
            "title": "真相大白",
            "summary": "苏糖帮助解开误会，顾北辰向林晓雨坦白心意。",
            "beats": ["苏糖说明误会真相。", "林晓雨开始动摇并产生悔意。", "顾北辰带着花来到门口直接表白。"],
            "scene_list": ["Scene 1: [下午] [室内] [苏糖家客厅] - 误会被解开，顾北辰携花现身。"],
        },
        {
            "episode": 6,
            "title": "幸福终章",
            "summary": "两人携手面对各自的过去，共同走向新的未来。",
            "beats": ["两人关系正式稳定。", "林晓雨说出自己的担忧。", "顾北辰给出承诺，两人走向未来。"],
            "scene_list": ["Scene 1: [夜] [室外] [城市街头] - 两人并肩漫步，在烟花下确认未来。"],
        },
    ],
}

MOCK_SCENES = [
    {
        "episode": 1,
        "title": "意外相遇",
        "scenes": [
            {
                "scene_number": 1,
                "scene_heading": "[夜] [室内] [科技发布会现场]",
                "environment_anchor": "科技发布会现场",
                "environment": "夜晚，赛博朋克风格的科技发布会现场，蓝紫色霓虹灯光，人群涌动，全息投影屏幕悬浮空中。",
                "lighting": "蓝紫色霓虹主光混合舞台冷白顶光",
                "mood": "闯入后的失控与对峙",
                "emotion_tags": [
                    {"target": "林晓雨", "emotion": "慌张", "intensity": 0.8},
                    {"target": "顾北辰", "emotion": "压迫", "intensity": 0.6},
                ],
                "key_props": ["文件夹", "全息投影屏幕"],
                "visual": "林晓雨手持文件夹，神色慌张地推开会场大门。台上顾北辰正在演讲，两人四目相对，空气瞬间凝固。镜头从顾北辰视角推近林晓雨惊慌的脸。",
                "key_actions": ["林晓雨推开会场大门", "顾北辰停下演讲看向她", "两人在人群前对视"],
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
                "scene_heading": "[白天] [室内] [设计公司会议室]",
                "environment_anchor": "设计公司会议室",
                "environment": "白天，现代化设计公司会议室，落地窗透入自然光，白色简约风格。",
                "lighting": "窗外自然天光为主，室内会议照明均匀补光",
                "mood": "职场压力下的克制对峙",
                "emotion_tags": [
                    {"target": "林晓雨", "emotion": "紧绷", "intensity": 0.7},
                    {"target": "顾北辰", "emotion": "审视", "intensity": 0.5},
                ],
                "key_props": ["投影屏幕", "提案文件"],
                "visual": "林晓雨站在投影屏幕前做提案，PPT 切换到关键页面。会议室门突然打开，顾北辰走进来，两人同时愣住，气氛瞬间凝固。",
                "key_actions": ["林晓雨切换提案页面", "顾北辰推门进入会议室", "两人停顿后重新进入对话"],
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
                "scene_heading": "[傍晚] [室外] [公司楼顶花园]",
                "environment_anchor": "公司楼顶花园",
                "environment": "傍晚，公司楼顶花园，夕阳将天空染成橙红色，微风吹动植物。",
                "lighting": "暖橙夕阳侧光配合楼顶环境自然反射光",
                "mood": "关系松动后的暧昧试探",
                "emotion_tags": [
                    {"target": "顾北辰", "emotion": "温柔", "intensity": 0.6},
                    {"target": "林晓雨", "emotion": "松动", "intensity": 0.5},
                ],
                "key_props": ["咖啡杯", "栏杆"],
                "visual": "顾北辰走向独自站在栏杆边的林晓雨，递出一杯咖啡。林晓雨接过，嘴角微微上扬，两人并肩望向城市天际线。",
                "key_actions": ["顾北辰递出咖啡", "林晓雨接过咖啡", "两人并肩望向天际线"],
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
                "scene_heading": "[夜] [室内] [高档餐厅包间]",
                "environment_anchor": "高档餐厅包间",
                "environment": "夜晚，高档餐厅包间，暖黄色烛光，玫瑰花装饰。",
                "lighting": "暖黄色烛光混合包间顶灯，走廊区域稍暗",
                "mood": "误会爆发前的压抑和刺痛",
                "emotion_tags": [
                    {"target": "林晓雨", "emotion": "受伤", "intensity": 0.8},
                    {"target": "顾北辰", "emotion": "错愕", "intensity": 0.6},
                ],
                "key_props": ["玫瑰花装饰", "包间门"],
                "visual": "林晓雨站在包间门口，看到顾北辰与一名女子亲密交谈，眼眶泛红。她缓缓转身离开。顾北辰追出来，只看到她消失在走廊尽头的背影。",
                "key_actions": ["林晓雨停在包间门口", "她转身离开", "顾北辰追到走廊"],
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
                "scene_heading": "[下午] [室内] [苏糖家客厅]",
                "environment_anchor": "苏糖家客厅",
                "environment": "下午，苏糖家温馨客厅，暖色调，沙发上摆着抱枕。",
                "lighting": "客厅暖色自然光配合室内柔和补光",
                "mood": "真相揭开后的迟疑与决心",
                "emotion_tags": [
                    {"target": "林晓雨", "emotion": "悔意", "intensity": 0.7},
                    {"target": "顾北辰", "emotion": "坚定", "intensity": 0.8},
                ],
                "key_props": ["抱枕", "白玫瑰"],
                "visual": "苏糖拉着林晓雨坐在沙发上，认真解释。林晓雨愣住，眼中闪过悔意。此时门铃响起，顾北辰出现在门口，手捧一束白玫瑰，眼神坚定。",
                "key_actions": ["苏糖拉林晓雨坐下解释", "林晓雨愣住后沉默", "顾北辰手捧白玫瑰出现在门口"],
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
                "scene_heading": "[夜] [室外] [城市街头]",
                "environment_anchor": "城市街头",
                "environment": "夜晚，繁华城市街头，万家灯火，远处烟花绽放。",
                "lighting": "城市街灯与远处烟花冷暖交错",
                "mood": "和解后的安定与温柔",
                "emotion_tags": [
                    {"target": "林晓雨", "emotion": "安心", "intensity": 0.6},
                    {"target": "顾北辰", "emotion": "承诺", "intensity": 0.6},
                ],
                "key_props": ["烟花", "街边灯光"],
                "visual": "两人手牵手漫步，林晓雨靠在顾北辰肩上。镜头缓缓拉远，两人身影融入城市灯光之中。",
                "key_actions": ["两人手牵手向前走", "林晓雨靠向顾北辰肩头", "两人继续走入街灯深处"],
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
        await repo.save_story(db, story_id, {
            "selected_setting": selected_setting,
            "meta": MOCK_OUTLINE["meta"],
            "characters": MOCK_OUTLINE["characters"],
            "relationships": MOCK_OUTLINE["relationships"],
            "outline": MOCK_OUTLINE["outline"],
            "scenes": [],
        })
        latest_story = await repo.get_story(db, story_id)
        return {
            "story_id": story_id,
            "meta": latest_story.get("meta") or {},
            "characters": latest_story.get("characters", []),
            "relationships": latest_story.get("relationships", []),
            "outline": latest_story.get("outline", []),
        }
    return {"story_id": story_id, **MOCK_OUTLINE}


async def mock_chat(
    story_id: str,
    message: str,
    db: AsyncSession = None,
    mode: str = "generic",
    context: Optional[dict] = None,
) -> AsyncGenerator[str, None]:
    if db:
        story = await repo.get_story(db, story_id)
    else:
        story = {}
    context = context or {}
    if mode == "character":
        reply = (
            "当前角色修改：强化人物性格与经历细节，保留姓名和主配角标签。\n"
            "对剧情的影响：基本不影响主线，仅让后续行为动机更清晰。"
        )
    elif mode == "episode":
        reply = (
            "当前剧情修改：把用户要求落实到本集冲突和转折中。\n"
            "对后续剧情的影响：后续集数按新的因果链顺延推进。"
        )
    elif mode == "outline":
        reply = (
            "当前大纲修改：按用户要求调整对应集数与关键事件。\n"
            "联动影响：相关人物动机和后续冲突会同步收紧。\n"
            "REFINE_JSON:{\"change_type\":\"episode\",\"change_summary\":\"按用户要求调整对应集数与关键事件，并同步后续推进\"}"
        )
    else:
        genre = story.get("genre", "现代")
        tone = story.get("tone", "热血")
        reply = f"建议按你的想法推进，保留{genre}风格与{tone}基调，并把修改落实为更清晰的冲突。"
    for char in reply:
        await asyncio.sleep(0.04)
        yield char


async def mock_generate_script(story_id: str) -> AsyncGenerator[dict, None]:
    for scene in MOCK_SCENES:
        await asyncio.sleep(0.3)
        yield scene


MOCK_WB_QUESTIONS = [
    {"dimension": "舞台选择", "text": "故事发生在哪个舞台？", "options": ["现代都市（豪门 / 职场 / 校园）", "古代架空（宫廷 / 江湖 / 世家）", "玄幻异能（都市异能 / 修仙 / 末世）"]},
    {"dimension": "人物规模", "text": "主要人物有几位？", "options": ["2位：男女主 CP，双强对决", "3位：三角关系，情感纠葛", "4-5位：群像叙事，多线并行"]},
    {"dimension": "主角类型", "text": "主角是哪种人？", "options": ["逆袭型：起点卑微，被欺后强势反转", "霸总型：天生强者，全程压制碾压", "双强碰撞：两个同量级的人激烈交锋"]},
    {"dimension": "核心钩子", "text": "故事最大的看点 / 钩子是什么？", "options": ["身份揭秘（隐藏大佬 / 替身 / 冒名顶替）", "复仇逆袭（打脸翻身 / 以牙还牙）", "禁忌之恋（对立阵营 / 不该爱的人）"]},
    {"dimension": "情感路线", "text": "感情线怎么走？", "options": ["甜宠路线：甜蜜为主，矛盾轻微", "先虐后甜：大虐大甜，催泪反转", "虐恋到底：全程高虐，以遗憾收场"]},
    {"dimension": "特色元素", "text": "加入哪种特色元素增强故事张力？", "options": ["悬疑反转（意外真相 / 多重身份）", "商战权谋（权力争夺 / 家族博弈）", "热血燃点（能力对决 / 绝地反击）"]},
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
