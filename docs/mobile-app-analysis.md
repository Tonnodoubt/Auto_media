# 手机 App 可行性分析

> 文档状态：专题可行性分析，仅供产品/部署评估参考；不作为当前 Web 主仓库实现口径。
> 生成日期：2026-03-24

---

## 一、现有架构概览

### 前端
- **框架**: Vue 3 + Vite 5
- **路由**: Vue Router 4（8 个页面：Step1~4、VideoGeneration、Settings、History）
- **状态管理**: Pinia + pinia-plugin-persistedstate（本地持久化到 localStorage）
- **UI**: 原生 HTML/CSS，无第三方组件库
- **通信**: REST API + SSE（流式响应）
- **响应式**: 无 media query，无 viewport 适配，桌面固定宽度布局

### 后端
- **框架**: FastAPI 0.111.0（Uvicorn 运行）
- **数据库**: SQLite（aiosqlite 异步驱动，文件 `automedia.db`）
- **ORM**: SQLAlchemy 2.0（AsyncSession）
- **本地依赖**: FFmpeg（合成音视频、提取帧）、edge-tts（微软 TTS）
- **文件存储**: 本地文件系统（`media/audio/`、`media/images/`、`media/videos/`）

### API Key 管理
三层优先级：
1. 前端请求 Headers（X-LLM-API-Key 等）→ 存储在浏览器 localStorage
2. 后端 `.env` 文件中的环境变量
3. 服务端配置默认值

### 架构本质
```
手机浏览器 / App
      ↓ HTTP
FastAPI (localhost:8000)   ← 当前是本地进程，这是移动化的核心瓶颈
      ├── SQLite 文件（automedia.db）
      ├── media/ 本地文件系统
      └── FFmpeg 本地进程 + edge-tts
```

---

## 二、三条移动化路径

### 路径 A：PWA（最快，约 1~2 周）
直接在前端加 `vite-plugin-pwa`，打包成可安装的渐进式 Web 应用。

| 项目 | 说明 |
|------|------|
| 改动量 | 极小，几乎不改业务代码 |
| 分发方式 | 浏览器"添加到主屏幕"，不上 App Store |
| 限制 | 后端仍需在本地或局域网服务器运行 |
| 适合场景 | 内部测试、个人使用 |

### 路径 B：Capacitor 套壳（中等，约 1~2 月）
用 Capacitor 将 Vue 应用包进原生 Shell，可以上架 App Store / Google Play。

| 项目 | 说明 |
|------|------|
| 前端复用率 | 高，Vue 代码大部分可用 |
| 必要前提 | 后端必须已迁移到云服务器 |
| 额外工作 | UI 响应式改造、原生权限（相机、文件等） |
| 适合场景 | 快速上线、预算有限 |

### 路径 C：云端后端 + 原生前端（完整产品，约 3~6 月）
正确的商业化路径：后端云化 + 前端重写（React Native 或 Flutter）。

| 项目 | 说明 |
|------|------|
| 体验 | 最佳，真正原生感 |
| 改动量 | 最大，前端需重写 |
| 后端 | FastAPI 本身适合云部署，改动集中在存储层 |
| 适合场景 | 正式产品上线、多用户 SaaS |

---

## 三、主要障碍逐项分析

| 障碍 | 当前状态 | 改造方向 | 难度 |
|------|----------|----------|------|
| **后端本地化** | localhost:8000 | 部署到云服务器（阿里云/AWS/Vercel）| ★★★ |
| **本地文件存储** | `media/` 目录下的视频/图片/音频 | 改为 OSS/S3 对象存储 | ★★★ |
| **SQLite** | 单文件数据库，不支持多用户 | 迁移到 PostgreSQL 或保持 SQLite（云端单实例）| ★★ |
| **FFmpeg 本地进程** | 直接调系统命令 | 保留在云端服务器，App 侧不感知 | ★（云化后自动解决）|
| **API Key 在 localStorage** | 浏览器本地存储，安全性低 | 账号系统 + 服务端托管 Key（SaaS 模式）| ★★★ |
| **无响应式布局** | 桌面固定宽度，无 media query | 重写 CSS，加 viewport meta，适配手机屏幕 | ★★ |
| **长任务通知** | 前端轮询 pipeline 状态 | 改为 WebSocket 推送或 APNs/FCM 通知 | ★★ |
| **视频文件大** | 生成后存本地，前端直接访问 | 使用 CDN 分发，App 流式播放 | ★★ |

---

## 四、优势（已有的好基础）

1. **FastAPI 本身就是生产级框架**，部署到云不需要重写，只改配置
2. **pipeline_executor.py 已完全异步化**，天然适合云端任务队列（Celery/ARQ）
3. **所有视频/图片/LLM 都是外部 API 调用**，不依赖本地算力，云端调用方式完全一致
4. **业务逻辑（Prompt、工作流）与存储解耦较好**，迁移存储层不影响核心逻辑
5. **前端 Vue 3 组件化良好**，响应式改造可以逐步推进

---

## 五、推荐路线图

### 阶段一：后端云化（必须先做）
```
SQLite → PostgreSQL（或 TiDB Serverless，免费额度够用）
media/ 本地文件 → 阿里云 OSS 或 AWS S3
部署 FastAPI 到云服务器（ECS/EC2 或容器化到 K8s）
加入用户注册/登录（JWT）
API Key 从 localStorage 移到服务端用户配置表
```

### 阶段二：前端响应式改造
```
加 viewport meta
所有固定 px 宽度改为 100%/vw/flex 布局
导航改为底部 TabBar（移动端惯例）
视频播放器适配竖屏
```

### 阶段三：App 封装上线
```
选项 A（快）：Capacitor 套壳 Vue，提交 App Store
选项 B（好）：用 React Native 重写前端，复用后端
```

---

## 六、结论

| 维度 | 评估 |
|------|------|
| **技术可行性** | 完全可以，无技术死角 |
| **最大工程量** | 后端云化 + 存储层迁移 |
| **前端复用率** | 业务逻辑 90% 可复用，UI 需要响应式改造 |
| **最快上线路径** | PWA（1~2周）或 Capacitor 套壳（后端云化后 1~2月）|
| **完整产品路径** | 3~6 个月（含云端部署、账号系统、UI 重构）|

**一句话总结：可以做，工程量中等。最大的变化在后端架构（本地→云），前端业务逻辑几乎不用动。**
