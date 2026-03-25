#!/usr/bin/env python3
"""
豆包首尾帧功能测试脚本

测试目标：
1. 验证豆包 Seedance 1.5 Pro 是否支持首尾帧输入
2. 对比单帧 I2V 和双帧过渡的质量差异
3. 评估过渡分镜方案的可行性

使用方法：
    python tests/test_doubao_first_last_frame.py
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.video import generate_video
from app.services.image import generate_image


IMAGE_API_KEY = os.getenv("TEST_IMAGE_API_KEY") or os.getenv("SILICONFLOW_API_KEY", "")
VIDEO_API_KEY = os.getenv("TEST_DOUBAO_VIDEO_API_KEY") or os.getenv("DOUBAO_API_KEY", "")
VIDEO_BASE_URL = os.getenv("TEST_DOUBAO_BASE_URL") or os.getenv("DOUBAO_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3"


def _require_manual_env() -> None:
    missing = []
    if not IMAGE_API_KEY:
        missing.append("TEST_IMAGE_API_KEY or SILICONFLOW_API_KEY")
    if not VIDEO_API_KEY:
        missing.append("TEST_DOUBAO_VIDEO_API_KEY or DOUBAO_API_KEY")
    if missing:
        raise RuntimeError(
            "Manual first/last-frame test requires env vars: " + ", ".join(missing)
        )


async def run_single_frame_i2v():
    """测试单帧 I2V（当前方案）"""
    print("\n" + "="*80)
    print("测试1：单帧 I2V（当前方案）")
    print("="*80)

    # 生成首帧图片
    print("\n[1/3] 生成首帧图片...")
    first_frame = await generate_image(
        visual_prompt="一个年轻男性站在办公室门口，穿着蓝色衬衫，现代办公室背景，温暖晨光，电影感，4k",
        shot_id="test_single_firstframe",
        model="black-forest-labs/FLUX.1-schnell",
        image_api_key=IMAGE_API_KEY,
        image_base_url="",
    )

    # 生成视频
    print("\n[2/3] 生成视频（单帧 I2V）...")
    video = await generate_video(
        image_url=f"http://localhost:8000{first_frame['image_url']}",
        prompt="年轻人从门口走到桌前坐下",
        shot_id="test_single_i2v",
        model="doubao-seedance-1-5-pro-251215",
        video_api_key=VIDEO_API_KEY,
        video_base_url=VIDEO_BASE_URL,
        video_provider="doubao",
    )

    print("\n[3/3] 测试完成！")
    print(f"  ✅ 首帧图片: {first_frame['image_url']}")
    print(f"  ✅ 视频路径: {video['video_url']}")

    return first_frame, video


async def run_first_last_frame_transition():
    """测试双帧过渡（新功能）"""
    print("\n" + "="*80)
    print("测试2：双帧过渡（新功能）")
    print("="*80)

    # 生成首帧图片
    print("\n[1/4] 生成首帧图片（人物站在门口）...")
    first_frame = await generate_image(
        visual_prompt="一个年轻男性站在办公室门口，穿着蓝色衬衫，站立姿势，现代办公室背景，温暖晨光，电影感，4k",
        shot_id="test_transition_firstframe",
        model="black-forest-labs/FLUX.1-schnell",
        image_api_key=IMAGE_API_KEY,
        image_base_url="",
    )

    # 生成尾帧图片
    print("\n[2/4] 生成尾帧图片（人物坐在椅子上）...")
    last_frame = await generate_image(
        visual_prompt="一个年轻男性坐在办公椅上，穿着蓝色衬衫，手放在膝盖上，现代办公室背景，温暖晨光，电影感，4k",
        shot_id="test_transition_lastframe",
        model="black-forest-labs/FLUX.1-schnell",
        image_api_key=IMAGE_API_KEY,
        image_base_url="",
    )

    # 生成过渡视频
    print("\n[3/4] 生成过渡视频（双帧）...")
    video = await generate_video(
        image_url=f"http://localhost:8000{first_frame['image_url']}",
        prompt="从站立姿势自然过渡到坐在椅子上",
        shot_id="test_transition_video",
        model="doubao-seedance-1-5-pro-251215",
        video_api_key=VIDEO_API_KEY,
        video_base_url=VIDEO_BASE_URL,
        video_provider="doubao",
        last_frame_url=f"http://localhost:8000{last_frame['image_url']}",  # ← 关键参数！
    )

    print("\n[4/4] 测试完成！")
    print(f"  ✅ 首帧图片: {first_frame['image_url']}")
    print(f"  ✅ 尾帧图片: {last_frame['image_url']}")
    print(f"  ✅ 过渡视频: {video['video_url']}")

    return first_frame, last_frame, video


async def run_scene_transition():
    """测试场景切换过渡"""
    print("\n" + "="*80)
    print("测试3：场景切换过渡")
    print("="*80)

    # 生成场景1最后一帧
    print("\n[1/4] 生成场景1最后一帧...")
    scene1_last = await generate_image(
        visual_prompt="年轻男性走出办公室门口，背影，回头看，现代办公室背景，电影感，4k",
        shot_id="test_scene1_lastframe",
        model="black-forest-labs/FLUX.1-schnell",
        image_api_key=IMAGE_API_KEY,
        image_base_url="",
    )

    # 生成场景2第一帧
    print("\n[2/4] 生成场景2第一帧...")
    scene2_first = await generate_image(
        visual_prompt="年轻男性走进会议室，侧面，现代会议室背景，自然光，电影感，4k",
        shot_id="test_scene2_firstframe",
        model="black-forest-labs/FLUX.1-schnell",
        image_api_key=IMAGE_API_KEY,
        image_base_url="",
    )

    # 生成过渡视频
    print("\n[3/4] 生成场景切换视频...")
    video = await generate_video(
        image_url=f"http://localhost:8000{scene1_last['image_url']}",
        prompt="平滑的场景切换，从办公室到会议室",
        shot_id="test_scene_transition",
        model="doubao-seedance-1-5-pro-251215",
        video_api_key=VIDEO_API_KEY,
        video_base_url=VIDEO_BASE_URL,
        video_provider="doubao",
        last_frame_url=f"http://localhost:8000{scene2_first['image_url']}",
    )

    print("\n[4/4] 测试完成！")
    print(f"  ✅ 场景1尾帧: {scene1_last['image_url']}")
    print(f"  ✅ 场景2首帧: {scene2_first['image_url']}")
    print(f"  ✅ 过渡视频: {video['video_url']}")

    return scene1_last, scene2_first, video


async def main():
    """运行所有测试"""
    _require_manual_env()
    print("\n" + "🔍 豆包首尾帧功能测试" + "\n")
    print("="*80)
    print("⚠️  注意：这是手动测试脚本，需要先配置环境变量。")
    print("   - 图像API: TEST_IMAGE_API_KEY 或 SILICONFLOW_API_KEY")
    print("   - 视频API: TEST_DOUBAO_VIDEO_API_KEY 或 DOUBAO_API_KEY")
    print("="*80)

    try:
        # 测试1：单帧 I2V
        await run_single_frame_i2v()

        # 测试2：双帧过渡
        await run_first_last_frame_transition()

        # 测试3：场景切换
        await run_scene_transition()

        print("\n" + "="*80)
        print("✅ 所有测试完成！")
        print("="*80)
        print("\n📊 对比分析：")
        print("1. 观察测试1（单帧）的视频质量")
        print("   - 人物是否准确到达目的地？")
        print("   - 动作是否流畅自然？")
        print("   - 结束姿势是否符合预期？")
        print()
        print("2. 观察测试2（双帧）的视频质量")
        print("   - 人物是否准确到达目的地？")
        print("   - 动作是否流畅自然？")
        print("   - 结束姿势是否与尾帧一致？")
        print()
        print("3. 观察测试3（场景切换）的视频质量")
        print("   - 场景切换是否平滑？")
        print("   - 视觉连贯性如何？")
        print()
        print("🎯 评估结论：")
        print("如果测试2和测试3的质量明显优于测试1，说明首尾帧功能确实有效！")
        print("="*80)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
