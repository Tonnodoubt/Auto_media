# 分镜切分问题深度分析

> 文档状态：历史分析稿。本文保留问题拆解和思路沉淀，当前实现口径请以 `README.md`、`docs/feature-documentation.md`、`docs/prompt-framework.md` 为准。
> **核心问题**：如何从剧本智能切分成镜头，每个镜头多长？
> **关键洞察**：不是所有镜头都需要5秒，关键在"镜头价值"判断

---

## 📊 当前SYSTEM_PROMPT的问题

### 问题1：时长固化（第146-150行）

**当前规则**：
```python
## DURATION GUIDELINES
- Action shots (movement, gesture): 3 seconds
- Dialogue shots: 4-5 seconds
- Establishing/atmosphere (no action): 4 seconds
- Close-up emotional beats: 3-4 seconds
```

**问题**：
- ❌ 没有1-2秒的选项
- ❌ 所有时长都偏长
- ❌ 没有"快速过渡镜头"的概念

---

### 问题2：切分粒度不灵活（第24行）

**当前规则**：
```python
- **DO NOT oversimplify:** Use 3-5 shots per major script event, not 1.
```

**导致的错误切分**：

#### 案例1：简单动作被过度拆分

```
剧本："李明走进办公室"

当前切分：
Shot 1: 李明走到门口 (3s)
Shot 2: 李明推开门 (3s)
Shot 3: 李明走进来 (3s)
Shot 4: 李明关上门 (3s)

问题：
- ❌ 简单动作拆成4个镜头
- ❌ 每个镜头3秒，太慢
- ❌ 总时长12秒，拖沓

应该：
Shot 1: 李明走进办公室 (2s，一个连续动作)
```

#### 案例2：情感复杂度判断错误

```
剧本："李明看到桌上的信封，愣住了，缓缓打开"

当前切分：
Shot 1: 李明看到信封 (3s)

问题：
- ❌ 情感变化压缩在一个镜头
- ❌ 错过了情绪递进的机会

应该：
Shot 1: 李明看到桌上的信封 (2s，快速发现)
Shot 2: 他的手停在半空 (3s，愣住的瞬间)
Shot 3: 手部特写，缓缓拿起信封 (4s，关键动作)
Shot 4: 眼睛特写，瞳孔微缩 (3s，情感高潮)
```

---

### 问题3：缺乏"镜头价值"判断

**当前缺失**：
- 没有区分"关键镜头"vs"过渡镜头"
- 没有"信息密度"的概念
- 没有"观众注意力"的节奏控制

---

## 💡 智能切分方案

### 核心概念：镜头价值分级

```
镜头价值 = 信息密度 × 情感强度 × 视觉冲击力
```

**3个等级**：

#### Level 1：快速过渡镜头（1-2秒）
```
特征：
- 信息密度低
- 无台词
- 简单动作
- 视觉过渡作用

示例：
- 转身看镜头
- 走过走廊
- 简单的眼神移动
- 物品位置切换

切分策略：
- 单个镜头，1-2秒
- 不需要拆分
- Prompt简洁
```

#### Level 2：标准叙事镜头（3-4秒）
```
特征：
- 中等信息密度
- 有动作或表情
- 可能有小动作
- 推进剧情

示例：
- 边走边说话
- 做出反应
- 物品交互
- 简单对话

切分策略：
- 单个镜头，3-4秒
- 包含1个核心动作
- Prompt适中
```

#### Level 3：关键镜头（4-5秒）
```
特征：
- 高信息密度
- 关键情感时刻
- 重要视觉细节
- 台词密集

示例：
- 情感爆发
- 关键发现
- 重要对话
- 视觉奇观

切分策略：
- 可以拆分成多个镜头
- 每个镜头3-5秒
- Prompt详细
```

---

## 🎯 改进方案：智能切分逻辑

### 修改SYSTEM_PROMPT

```python
## SMART SHOT DURATION & SPLITTING (替代第146-150行)

### SHOT VALUE ASSESSMENT (镜头价值评估)

Before creating shots, **evaluate each script segment's visual value**:

**Level 1: Quick Transition Shots (1-2 seconds)**
- Simple physical movements (turning head, walking, simple gestures)
- No dialogue or emotional weight
- Purpose: Smooth visual transition between important shots
- Example: "He turns to look at the window" → 1 shot, 2 seconds, simple prompt

**Level 2: Standard Narrative Shots (3-4 seconds)**
- Medium complexity (walking + talking, picking up objects, facial reactions)
- Simple dialogue (one short line)
- Purpose: Advance the story
- Example: "He picks up the phone and answers" → 1 shot, 3 seconds

**Level 3: Key Moments (4-5 seconds each, may split into multiple shots)**
- High emotional intensity (shock, realization, conflict)
- Critical plot points (discoveries, decisions, confrontations)
- Dense information (complex actions + dialogue)
- Visual spectacle (special effects, dramatic reveals)

**SPLITTING RULES**:
- **NEVER split Level 1 actions** (keep as one 1-2s shot)
- **Usually one Level 2 action per shot** (unless dialogue requires splitting)
- **ALWAYS split Level 3 moments** into 2-4 shots showing progression:
  - Setup shot (establish context)
  - Reaction shot (emotional response)
  - Detail shot (critical visual element)
  - Resolution shot (aftermath)

### DURATION GUIDELINES

**Per shot duration (flexible based on value level)**:
- Level 1 (transition): 1-2 seconds
- Level 2 (standard): 3-4 seconds
- Level 3 (key moment): 4-5 seconds per shot

**Total scene duration control**:
- Simple action (e.g., "walks in"): 1 shot, 2 seconds
- Standard action (e.g., "sits down"): 1 shot, 3 seconds
- Complex action (e.g., "angrily stands up"): 2 shots, 3s each = 6 seconds
- Emotional climax (e.g., "realizes the truth"): 3-4 shots, 4-5s each = 12-20 seconds

**Dialogue matching**:
- Short line (1 sentence): 1 shot, 3-4 seconds
- Medium line (2-3 sentences): Split into 2 shots, 3-4s each
- Long emotional speech: Split into multiple reaction shots, 4-5s each

### EXAMPLE TRANSFORMATION

**Script**: "李明走进办公室，看到桌上的信封，愣了一下，缓缓打开"

**Current (wrong) approach**:
- Shot 1: 李明走进办公室 (3s)
- Shot 2: 李明看到信封 (3s)
- Shot 3: 李明打开信封 (3s)
Total: 9 seconds, flat pacing

**Smart approach**:
- Shot 1 (Level 1): 李明走进办公室 (2s) ← Quick transition
- Shot 2 (Level 3): 李明看到桌上的信封 (4s) ← Key moment starts
- Shot 3 (Level 3): 他的手停在半空，眼神凝固 (4s) ← Emotional reaction
- Shot 4 (Level 3): 手部特写，缓缓拿起信封 (5s) ← Critical action
- Shot 5 (Level 3): 眼睛特写，瞳孔微缩 (4s) ← Emotional peak
Total: 19 seconds, proper emotional buildup

**Why smart is better**:
- ✅ Quick entry (not dragging)
- ✅ Emotional buildup (not flat)
- ✅ Visual variety (WS → CU → ECU)
- ✅ Audience engagement (pacing)
```

---

## 📊 对比示例

### 场景1：简单走路

**剧本**："李明从门口走到桌子前"

```
当前切分（错误）：
Shot 1: 李明在门口 (3s)
Shot 2: 李明走到中间 (3s)
Shot 3: 李明到达桌子 (3s)
总时长：9秒，拖沓

智能切分：
Shot 1: 李明从门口走向桌子 (2s)
总时长：2秒，干脆
```

---

### 场景2：情感发现

**剧本**："李明看到屏幕上的消息，震惊，后退一步"

```
当前切分（错误）：
Shot 1: 李明看到消息，震惊，后退 (4s)
总时长：4秒，匆忙

智能切分：
Shot 1: 李明看向屏幕 (2s) ← Level 1
Shot 2: 屏幕内容特写 (3s) ← Level 2
Shot 3: 李明的眼睛，瞳孔剧烈收缩 (4s) ← Level 3
Shot 4: 他的身体后退一步 (3s) ← Level 2
Shot 5: 手部特写，手指颤抖 (4s) ← Level 3
总时长：16秒，情感递进
```

---

## 🎯 实施建议

### 方案1：立即修改SYSTEM_PROMPT（1小时）

**修改点**：
1. 第24行：删除"Use 3-5 shots per major event"
2. 第146-150行：替换为"SMART SHOT DURATION & SPLITTING"
3. 添加"镜头价值评估"示例

**预期效果**：
- 减少40%的冗余镜头
- 提升情感高潮的镜头密度
- 视频总时长更合理

---

### 方案2：添加自动时长估算（2小时）

**在Shot Schema中添加**：
```python
class Shot(BaseModel):
    ...
    shot_value_level: Literal[1, 2, 3] = Field(
        default=2,
        description="镜头价值等级：1=快速过渡，2=标准叙事，3=关键时刻"
    )

    # 根据等级自动调整时长
    def get_estimated_duration(self) -> int:
        if self.shot_value_level == 1:
            return 2
        elif self.shot_value_level == 2:
            return 3
        else:
            return 5
```

---

## 💰 成本影响

**当前方案**（固定3-5秒）：
- 10个场景，每场景3镜头 = 30镜头
- 平均4秒/镜头 = 120秒视频
- API成本：30 × ¥0.15 = ¥4.5

**智能方案**（动态1-5秒）：
- Level 1: 8镜头 × 2秒 = 16秒
- Level 2: 15镜头 × 3秒 = 45秒
- Level 3: 7镜头 × 5秒 = 35秒
- 总计：30镜头，96秒视频
- API成本：30 × ¥0.15 = ¥4.5（但时长减少20%）

**质量提升**：节奏更合理，情感递进更好

---

## 🚀 我的建议

**立即实施**：
1. 修改SYSTEM_PROMPT，添加"SMART SHOT DURATION & SPLITTING"
2. 测试3-5个场景，看切分质量
3. 根据效果微调

需要我立即帮你修改SYSTEM_PROMPT吗？我可以直接改代码！💪
