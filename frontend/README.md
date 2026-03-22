# Auto Media Frontend

基于 Vue 3 的 AI 短剧生成向导，引导用户从创意输入到剧本生成、视频合成的完整流程。

---

## 快速开始

### 环境要求

- Node.js 18+
- npm

### 安装依赖

```bash
npm install
```

### 启动开发服务器

```bash
npm run dev
```

默认运行在 `http://localhost:5173`，需要后端服务同时运行在 `http://localhost:8000`。

### 构建生产版本

```bash
npm run build
```

---

## 项目结构

```
frontend/
├── src/
│   ├── main.js                    # 应用入口
│   ├── App.vue                    # 根组件
│   ├── router/
│   │   └── index.js               # 路由定义
│   ├── stores/
│   │   ├── story.js               # 故事流程全局状态
│   │   └── settings.js            # API 配置状态（双组 Key + 回退链）
│   ├── api/
│   │   └── story.js               # 后端 API 调用封装（统一 Header 注入）
│   ├── views/
│   │   ├── Step1Inspire.vue       # 灵感输入
│   │   ├── Step2Settings.vue      # 世界构建
│   │   ├── Step3Script.vue        # 剧本生成
│   │   ├── Step4Preview.vue       # 预览导出
│   │   ├── VideoGeneration.vue    # 视频流水线
│   │   └── SettingsView.vue       # 设置页
│   ├── components/
│   │   ├── StepIndicator.vue      # 步骤进度条
│   │   ├── StyleSelector.vue      # 风格选择
│   │   ├── FollowUpOptions.vue    # 追问选项
│   │   ├── OutlinePreview.vue     # 大纲预览
│   │   ├── CharacterGraph.vue     # 角色关系图（SVG）
│   │   ├── CharacterDesign.vue    # 角色设计 + 图像生成
│   │   ├── SceneStream.vue        # 场景流式渲染
│   │   ├── OutlineChatPanel.vue   # AI 大纲修改面板
│   │   ├── EpisodeChatPanel.vue   # 章节专属 AI 对话
│   │   ├── CharacterChatPanel.vue # 角色专属 AI 对话
│   │   ├── ExportPanel.vue        # 导出
│   │   └── ApiKeyModal.vue        # API Key 提示弹窗
│   └── style.css
├── vite.config.js                 # Vite 配置（含 API 代理）
└── package.json
```

### 技术栈

| 层级 | 技术 |
|------|------|
| 框架 | Vue 3 (Composition API + `<script setup>`) |
| 构建工具 | Vite 5 |
| 路由 | Vue Router 4 |
| 状态管理 | Pinia 2 |
| HTTP | Fetch API（含 SSE 流式处理） |

---

## 功能流程

```
Step 1 /step1          输入创意 + 选择风格
    ↓ POST /world-building/start + /turn
Step 2 /step2          6 轮引导式世界构建问答
    ↓ POST /generate-outline
Step 3 /step3          大纲 + 角色关系图 + 流式剧本生成
    ↓
Step 4 /step4          预览完整剧本 + 导出 JSON
    ↓
/video-generation       视频流水线（分镜 → TTS → 图片 → 视频）
```

### Step 1 — 灵感输入

- 文本框输入故事创意，支持随机灵感盲盒（6 维度随机生成）
- 风格选择：现代 / 古装 / 悬疑 / 甜宠
- 未设置 API Key 时弹窗提示

### Step 2 — 世界构建

- AI 返回故事设定选项，支持自定义输入
- 可与 AI 实时对话完善设定（SSE 流式返回）
- AI 回复完成后自动更新"你的灵感"区域

### Step 3 — 剧本生成

- 左侧：大纲预览（元信息、人物卡片、分集结构）
- 右侧（sticky）：角色关系图（SVG 环形布局 + 带箭头关系标签）+ 角色图像设计
- 流式渲染场景（场景描述 + 角色对话）
- 右上角 AI 修改助手（OutlineChatPanel）

### Step 4 — 预览导出

- 汇总展示：集数、角色数、场景数
- 完整剧本场景列表
- 导出为 JSON 文件
- 重新创作按钮（清空所有状态）

### 视频生成页

- 输入剧本 → 解析分镜
- TTS 语音生成（18+ 中文语音）
- 场景图片生成（FLUX.1-schnell，1280×720）
- 图生视频（Wan2.6-i2v，DashScope）
- 一键自动全流程 + 实时进度展示

---

## 状态管理

### story store (`src/stores/story.js`)

```javascript
{
  currentStep: 1,
  storyId: null,
  input: { idea: '', style: '' },
  followUpOptions: [],
  selectedSetting: '',
  meta: null,               // { title, genre, episodes, theme }
  characters: [],           // [{ name, role, description }]
  relationships: [],        // [{ source, target, label }]
  outline: [],              // [{ episode, title, summary }]
  scenes: []                // [{ episode, title, scenes: [...] }]
}
```

### settings store (`src/stores/settings.js`)

双组 Key 设计：基础 LLM 配置 + 高级专用配置，各字段均存入 `localStorage`。

```javascript
// 状态字段
{
  backendUrl: '',        // 后端地址，留空走 Vite 代理
  provider: 'claude',   // 默认 LLM 服务商
  llmBaseUrl: '',        // 默认 LLM Base URL
  apiKey: '',            // 默认 LLM API Key

  // 高级：文本生成专用（为空时回退到上方）
  textProvider: '',
  textBaseUrl: '',
  textApiKey: '',

  // 高级：图片 / 视频生成专用（为空时回退到 apiKey）
  imageApiKey: '',       // SiliconFlow Key
  videoApiKey: '',       // DashScope Key
}

// Getters（实际使用的有效值）
{
  useMock,               // !textApiKey && !apiKey
  effectiveLlmApiKey,    // textApiKey || apiKey
  effectiveLlmProvider,  // textProvider || provider
  effectiveLlmBaseUrl,   // textBaseUrl || llmBaseUrl
  effectiveImageApiKey,  // imageApiKey || apiKey
  effectiveVideoApiKey,  // videoApiKey || apiKey
}
```

---

## API 封装

`src/api/story.js` 封装所有后端调用，所有请求自动携带统一 Headers。

### 请求头（`getHeaders()`）

```javascript
{
  'Content-Type':    'application/json',
  'X-LLM-API-Key':  settings.effectiveLlmApiKey,
  'X-LLM-Base-URL': settings.effectiveLlmBaseUrl,
  'X-LLM-Provider': settings.effectiveLlmProvider,
  'X-Image-API-Key': settings.effectiveImageApiKey,
  'X-Video-API-Key': settings.effectiveVideoApiKey,
}
```

### 接口列表

```javascript
// 故事生成
analyzeIdea(idea, genre, tone)
worldBuildingStart(idea)
worldBuildingTurn(storyId, answer)
generateOutline(storyId, selectedSetting)
refineStory(storyId, changeType, changeSummary)

// SSE 流式
streamChat(storyId, message, onChunk, onDone, onError)
streamScript(storyId, onScene, onDone, onError)

// 流水线
startStoryboard(storyId, script, provider)   // → POST body
getPipelineStatus(storyId)

// 角色图像
generateCharacterImage(storyId, character)
generateAllCharacterImages(storyId, characters)
getCharacterImages(storyId)
```

后端地址通过 `settings.backendUrl` 配置，留空走 Vite 代理 `/api → localhost:8000`。

---

## 组件说明

| 组件 | 用途 |
|------|------|
| `StepIndicator` | 顶部步骤进度条，右上角含"⚙ 设置"按钮 |
| `StyleSelector` | 风格选择按钮组（支持 v-model） |
| `FollowUpOptions` | 预设选项 + 自定义输入框 + AI 对话按钮 |
| `OutlinePreview` | 故事元数据、人物卡片、分集大纲 |
| `CharacterGraph` | SVG 人物关系图谱，节点环形布局，带箭头和关系标签 |
| `CharacterDesign` | 角色设计轮播，支持逐个或批量调用后端图像生成 API |
| `SceneStream` | 渲染场景描述和角色对话，支持流式加载动画 |
| `OutlineChatPanel` | 抽屉式 AI 大纲修改面板，SSE 流式输出 |
| `EpisodeChatPanel` | 章节专属 AI 对话 |
| `CharacterChatPanel` | 角色专属 AI 对话 |
| `ExportPanel` | 将完整剧本数据导出为 JSON 文件 |
| `ApiKeyModal` | API Key 缺失或无效时的弹窗提示，引导前往设置 |

---

## 设置页 (`/settings`)

- **后端地址**：FastAPI 服务地址，留空走代理
- **LLM 配置**：服务商选择（自动填入 Base URL）+ API Key
- **高级 API 设置**（可折叠）：
  - 文本生成专用：服务商 / Base URL / API Key（优先于 LLM 配置）
  - 图片/视频生成专用：SiliconFlow Key / DashScope Key（优先于通用 Key）

支持的服务商：Anthropic Claude / OpenAI / 阿里云 Qwen / 智谱 GLM / Google Gemini / 自定义

---

## 样式规范

| 属性 | 值 |
|------|-----|
| 主色 | `#6c63ff`（紫色） |
| 辅助色 | `#a78bfa` |
| 中性色 | `#e0e0e0` |
| 错误色 | `#e53935` |
| 成功色 | `#4caf50` |
| 内容区最大宽度 | `600px`（Step 3 / 视频页为 `900px` 左右布局） |
| 场景卡片动画 | 淡入 + 流式加载弹跳指示器 |
