# AutoMedia Frontend

前端是一个基于 Vue 3 的多步骤创作界面，负责承接从灵感输入到剧本生成，再到视频流水线的完整交互。

## 环境要求

- Node.js 20+
- npm

## 启动

```bash
npm install
npm run dev
```

默认地址为 `http://localhost:5173`。  
开发时通常需要后端同时运行在 `http://localhost:8000`。

构建命令：

```bash
npm run build
```

## 主要页面

- `src/views/Step1Inspire.vue`
  - 灵感输入
  - 故事题材约束
  - 组合灵感生成器
  - AI 定向改写
- `src/views/Step2Settings.vue`
  - 6 轮世界观构建
  - 完成后前往剧本生成
  - 重新构建世界观
- `src/views/Step3Script.vue`
  - 自定义集数
  - 流式剧本生成
  - 剧本继续生成
  - 视觉风格设置
- `src/views/Step4Preview.vue`
  - 预览与导出
- `src/views/VideoGeneration.vue`
  - 分镜、图片、TTS、视频、拼接
- `src/views/SettingsView.vue`
  - LLM / 图片 / 视频 provider 配置

## 主要组件

- `src/components/IdeaGenerator.vue`
- `src/components/ArtStyleSelector.vue`
- `src/components/OutlinePreview.vue`
- `src/components/SceneStream.vue`
- `src/components/CharacterGraph.vue`
- `src/components/CharacterDesign.vue`
- `src/components/OutlineChatPanel.vue`

## 状态与接口

- `src/stores/story.js`
  - 当前故事主状态
- `src/stores/settings.js`
  - API Key、Provider、Base URL、本地持久化配置
- `src/api/story.js`
  - 与后端主流程 API 的通信封装

## 说明

- 前端会把用户保存的配置持久化到浏览器本地
- 实际请求时会按“页面设置优先，后端 `.env` 回退”的方式工作
- 根目录 [README.md](../README.md) 是项目总说明，前端本文档只保留前端侧开发口径
