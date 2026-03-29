# 阿里云 ECS + FRP 单端口临时试用实施文档

> 日期：2026-03-29  
> 面向对象：当前项目维护者  
> 目标：把 AutoMedia 以“单端口同源入口”的方式临时开放给少量指定人员试用，试用人员只访问前端入口，后端不作为独立地址暴露。

## 1. 实施目标

最终对试用人员只提供一个地址：

```text
http://<ECS公网IP>:18080
```

访问链路为：

```text
试用人员浏览器
  -> ECS:18080
  -> frps
  -> frpc
  -> 本机 127.0.0.1:8080
     |- /        -> frontend/dist
     |- /api     -> 127.0.0.1:8000
     |- /health  -> 127.0.0.1:8000
     |- /media   -> 127.0.0.1:8000
```

---

## 2. 实施前确认

开始前先确认下面几件事：

1. 阿里云 ECS 已有公网 IPv4，或已绑定 EIP
2. 本机可以主动访问 ECS
3. 本机 AutoMedia 后端可正常启动在 `127.0.0.1:8000`
4. 本机可以打包前端
5. 服务端 `.env` 已准备好试用所需的真实凭证

建议至少确认这些服务端凭证可用：

- LLM
- Script LLM
- 图片生成
- 视频生成

如果当前还是 HTTP，对试用人员不要开放真实第三方 Key 填写能力。

---

## 3. ECS 侧实施

## 3.1 安全组放行

只放行下面端口：

| 端口 | 用途 |
|------|------|
| `7000/tcp` | `frps` 控制连接端口 |
| `18080/tcp` | 对外统一入口 |
| `7500/tcp` | `frps` Dashboard，可选 |

不开放：

- `15173`
- `18000`

## 3.2 安装 `frps`

推荐目录：

- `/opt/frp`
- `/etc/frp`

`/etc/frp/frps.toml`

```toml
bindPort = 7000

auth.method = "token"
auth.token = "CHANGE_ME_TO_A_STRONG_TOKEN"

transport.tls.force = true

webServer.addr = "127.0.0.1"
webServer.port = 7500
webServer.user = "admin"
webServer.password = "CHANGE_ME_TO_A_STRONG_PASSWORD"
```

## 3.3 配置 systemd

`/etc/systemd/system/frps.service`

```ini
[Unit]
Description=frp server
After=network.target

[Service]
Type=simple
ExecStart=/opt/frp/frps -c /etc/frp/frps.toml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now frps
sudo systemctl status frps
```

---

## 4. 本机后端实施

## 4.1 准备 `.env`

确保后端 `.env` 已配置好试用所需的默认凭证。

重点不是“能否打开首页”，而是试用时是否能实际跑通这些能力：

- 故事生成
- 脚本生成
- 角色图生成
- 图片生成
- 视频生成
- TTS

## 4.2 启动后端

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

本地自检：

```text
http://127.0.0.1:8000/health
```

如果这里不正常，不要继续做 FRP。

---

## 5. 本机前端实施

## 5.1 打包前端

```powershell
cd frontend
npm run build
```

补充：

- 建议使用 Node 20/22 LTS 执行前端构建
- 当前工作环境中的 Node 24 与现有 `vite@5` 组合存在 HTML 入口构建兼容问题，若遇到打包报错，请先切换到 LTS 版本再执行

打包产物应位于：

```text
frontend/dist
```

## 5.2 统一入口要求

> 更新说明：当前代码已经支持 FastAPI 在存在 `frontend/dist` 时直接托管前端，并为 SPA 路由做回退；如果文档下方还有“`/` 只返回 API JSON、不能当前端入口”的旧描述，以代码现状为准，应视为历史说明。

你需要在本机准备一个统一入口 `127.0.0.1:8080`，它必须同时做到：

1. `/` 返回前端页面
2. 托管 `frontend/dist`
3. `/api` 转发到 `127.0.0.1:8000`
4. `/health` 转发到 `127.0.0.1:8000`
5. `/media` 转发到 `127.0.0.1:8000`
6. 前端路由刷新时回退到 `index.html`
7. SSE 不被代理缓冲
8. `/media` 原样透传，不被错误重写

可选实现：

- Nginx
- Caddy
- 其他反向代理或静态文件服务器

不建议直接把 FastAPI 根路径当成前端入口，因为当前项目里 `/` 返回的是 API 说明 JSON，不是前端页面。

---

## 6. 本机 `frpc` 实施

`C:\frp\frpc.toml`

```toml
serverAddr = "<ECS公网IP>"
serverPort = 7000

auth.method = "token"
auth.token = "CHANGE_ME_TO_A_STRONG_TOKEN"

loginFailExit = true

[[proxies]]
name = "automedia-web"
type = "tcp"
localIP = "127.0.0.1"
localPort = 8080
remotePort = 18080
```

启动：

```powershell
C:\frp\frpc.exe -c C:\frp\frpc.toml
```

---

## 7. 本机验收顺序

按下面顺序验收，不要跳步：

## 7.1 先验本机统一入口

浏览器打开：

```text
http://127.0.0.1:8080
http://127.0.0.1:8080/health
```

确认：

- 首页可打开
- `health` 正常
- 前端控制台没有请求跳到 `http://localhost:8000/...`

## 7.2 再验 ECS 公网入口

浏览器打开：

```text
http://<ECS公网IP>:18080
http://<ECS公网IP>:18080/health
```

确认：

- 首页可打开
- `health` 正常
- 静态资源加载正常

## 7.3 再验前端设置

首次进入页面后，在设置页明确填写：

```text
backendUrl = http://<ECS公网IP>:18080
```

注意：

- 这是浏览器本地设置
- 换浏览器、换设备、无痕窗口都可能需要重新设置
- 设置页里如果看到 “留空使用默认 `http://localhost:8000`”，不要按这个提示配置，它只是开发遗留文案

---

## 8. 业务验收清单

## 8.1 API 传输

确认下面请求都走统一入口：

- `/api/v1/story/...`
- `/api/v1/pipeline/...`
- `/api/v1/character/...`
- `/api/v1/image/...`
- `/api/v1/video/...`
- `/api/v1/tts/...`

浏览器里不应出现：

```text
http://localhost:8000/...
```

## 8.2 存储

确认这些能力可正常保存与恢复：

- 历史列表可读取
- 旧故事可加载
- 分镜状态可恢复
- 生成文件 URL 可恢复
- 最终视频链接可恢复

## 8.3 提示词与资产链路

确认下面链路可正常工作：

- 画风预设可正常透传
- 环境/场景参考资产可生成
- `scene_reference_assets` / `episode_reference_assets` 可正常回写
- 角色图、图片、视频生成时能走统一入口后的同源资源地址

## 8.4 媒体链路

确认：

- 角色图能显示
- TTS 音频能播放
- 图片生成结果可访问
- 视频生成结果可访问
- 视频拼接结果可播放

---

## 9. 给试用人员的最小说明

发给试用人员的说明尽量压缩成下面几条：

1. 只打开这个地址：`http://<ECS公网IP>:18080`
2. 不要访问 `/docs`
3. 不要访问其他端口
4. 首次进入设置页后，把 `backendUrl` 填成 `http://<ECS公网IP>:18080`
5. 如果当前还是 HTTP，不要填写真实第三方 API Key

也就是说，试用人员只操作前端页面，不需要理解后端结构。

---

## 10. 常见故障排查

| 现象 | 优先排查 |
|------|---------|
| 首页能开，但角色图不显示 | `backendUrl` 是否没填；`/media` 是否未原样透传 |
| 视频页能进，但生成失败 | 是否误进 Mock；服务端 `.env` 是否缺凭证 |
| 浏览器报跨域错误 | 是否仍在走分端口访问，而不是统一入口 |
| 流式内容卡住 | 代理层是否对 SSE 做了缓冲 |
| 媒体 URL 返回 404 | `/media` 是否被错误重写 |
| 换浏览器后功能突然不正常 | `backendUrl` 是本地浏览器设置，需重新填写 |
| 页面像是模拟数据 | `useMock` 是否仍为真 |

---

## 11. 实施概况

这次实施的本质不是“把前端和后端分别暴露到公网”，而是：

**通过 ECS + FRP 暴露一个统一前端入口，让本机 `8080` 承接整个 Web 应用的同源访问，试用人员只看到前端，后端退到幕后通信。**

如果后续目标升级为：

- 不需要手动填写 `backendUrl`
- 不受前端 Mock 逻辑影响
- 用户可安全填写自己的真实第三方 Key
- 长期稳定对外开放

那就需要进入代码修复和正式部署阶段，不再只是这一份实施文档能解决的问题。
