# 阿里云 ECS + FRP 单端口临时试用方案

> 文档状态：部署参考方案，不属于当前核心开发文档；仅在临时公网试用或同源转发场景下参考。

> 日期：2026-03-30  
> 状态：面向单端口同源入口目标的推荐方案  
> 目标：让少量指定人员只通过一个前端入口临时试用 AutoMedia，后端只负责同源通信，不要求用户额外访问后端地址。

## 快速结论

1. **只推荐单端口同源方案。**
2. **对试用人员只暴露一个地址：`http://<ECS公网IP>:18080`。**
3. **试用人员只操作前端页面，不需要访问 `/docs`、后端端口或本地开发地址。**
4. **要尽量完整可用，建议由本机统一入口 `8080` 同时承接前端页面、API、`/health` 和 `/media`。**
5. **如果仍是纯 HTTP，不要让试用人员在前端填写真实第三方 API Key；优先使用服务端 `.env` 里的默认 Key。**

---

## 1. 适用范围

本文只解决下面这个目标：

- 给少量指定人员临时试用
- 他们只打开一个前端地址
- 后端接口对他们是透明的，只在前端背后正常通信
- 当前代码需要尽量向单端口同源目标收敛

本文**不**解决下面这些目标：

- 正式公网发布
- 面向不特定用户传播
- 打开网址即零配置
- 长期稳定运营
- 让用户在 HTTP 页面里安全填写自己的真实第三方 Key

---

## 2. 推荐方案

推荐结构如下：

```text
试用人员浏览器
        |
        v
http://<ECS公网IP>:18080
        |
        v
阿里云 ECS:18080
        |
        v
frps
        |
        v
frpc
        |
        v
本机 127.0.0.1:8080
   |- /        -> 前端页面
   |- /api     -> 127.0.0.1:8000
   |- /health  -> 127.0.0.1:8000
   |- /media   -> 127.0.0.1:8000
```

这套方案的核心原则只有一条：

**用户侧只看到一个前端入口，前端、接口、媒体全部走同一个公网 origin。**

---

## 3. 为什么只保留这一种方案

当前仓库的目标决定了“前后端分开暴露”不适合作为试用方案，原因已经能从代码里直接确认：

1. 后端当前 `CORS` 只允许 `http://localhost:5173`  
   见 `app/main.py`

2. 前端的 `backendUrl` 仍保存在浏览器本地 `localStorage`，不是服务端统一配置  
   见 `frontend/src/stores/settings.js`

3. 前端现在应优先使用同源地址，避免请求回落到 `http://localhost:8000`  
   见 `frontend/src/utils/backend.js`  
   见 `frontend/src/views/SettingsView.vue`

4. 当前前端仍保留 Mock 逻辑，但已改为显式开启  
   只有设置 `VITE_ENABLE_MOCK=true` 时，`useMock = MOCK_ENABLED && !llmApiKey`  
   见 `frontend/src/stores/settings.js`

5. FastAPI 在存在 `frontend/dist` 时已经可以直接托管前端，并为 SPA 路由做回退  
   见 `app/main.py`

6. 视频相关链路依赖同源 `/media/videos/...`  
   见 `app/routers/pipeline.py` 和 `app/services/ffmpeg.py`

因此，如果你要满足“别人只用前端，后端只是正常通信、无需额外访问”，就必须把访问收敛成一个同源入口，而不是分别暴露前端和后端端口。

---

## 4. 当前代码下的关键限制

下面这些限制不会因为用了 FRP 自动消失，文档必须明确写出来：

### 4.1 `backendUrl` 以同源留空为默认方案

当前代码下，优先目标应当是：

- 同源部署时让 `backendUrl` 保持为空
- 前端默认使用当前站点 origin
- 只有前后端跨 origin 部署时，才手动填写 `backendUrl`

仍需注意：

- `backendUrl` 是浏览器本地设置，不是服务端全局配置
- 换浏览器、换设备、无痕窗口重开，都可能需要重新检查
- 如果你选择跨 origin 部署，再把 `backendUrl` 明确填成对应后端地址

### 4.2 Mock 模式仍可能影响“真实功能试用”

当前代码中：

- `MOCK_ENABLED` 仅在显式设置 `VITE_ENABLE_MOCK=true` 时开启
- `useMock` 仍取决于浏览器本地是否存在 `llmApiKey`

这意味着：

- 默认情况下，前端会保持真实模式，允许后端继续使用 `.env` 默认 LLM 配置
- 只有在前端明确开启 Mock 环境变量时，浏览器本地无 `llmApiKey` 的流程才会进入 Mock 分支

如果你的目标是“尽量完整试用真实功能”，不要在前端构建环境里打开 `VITE_ENABLE_MOCK=true`。

### 4.3 HTTP 下不要让试用人员填写真实第三方 Key

当前前端会把：

- `backendUrl`
- `llmApiKey`
- `scriptApiKey`
- `imageApiKey`
- `videoApiKey`

保存在浏览器本地，并通过请求头发送给后端。

因此如果统一入口仍是：

```text
http://<ECS公网IP>:18080
```

就不要让试用人员在前端填写真实第三方 Key。更稳妥的做法是：

1. 服务端 `.env` 预置所需 Key
2. 同源部署时前端不必填写 `backendUrl`
3. 如果后续必须让用户自己填真实 Key，再先升级到 HTTPS

---

## 5. 部署要求

## 5.1 ECS 要求

- 有公网 IPv4，或绑定 EIP
- 到本机 `frpc` 的连接稳定
- 安全组按最小开放原则配置

## 5.2 安全组建议

推荐只开放下面这些端口：

| 端口 | 用途 | 是否必须 |
|------|------|---------|
| `7000/tcp` | `frps` 控制连接端口 | 必须 |
| `18080/tcp` | 对外统一 Web 入口 | 必须 |
| `7500/tcp` | `frps` Dashboard 管理端口 | 可选 |

不建议开放：

- `15173/tcp`
- `18000/tcp`

因为当前目标不是让用户直接访问前后端两个端口，而是只给他们一个统一前端入口。

---

## 6. FRP 配置

## 6.1 ECS 侧 `frps.toml`

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

说明：

- `7000` 是本机 `frpc` 连上来的控制端口
- 强制 TLS
- Dashboard 只监听本机，不直接暴露公网

## 6.2 ECS 侧 `systemd` 服务

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

启动命令：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now frps
sudo systemctl status frps
```

## 6.3 本机侧 `frpc.toml`

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

如果本机是 Windows，例如：

- `C:\frp\frpc.exe`
- `C:\frp\frpc.toml`

启动：

```powershell
C:\frp\frpc.exe -c C:\frp\frpc.toml
```

---

## 7. 本机统一入口 `8080` 的要求

`8080` 这一层是整个方案能不能成立的关键。

它不能只是“有个端口”，而必须同时做到：

1. 托管前端打包产物 `frontend/dist`
2. `/` 返回前端页面
3. `/api` 转发到 `127.0.0.1:8000`
4. `/health` 转发到 `127.0.0.1:8000`
5. `/media` 转发到 `127.0.0.1:8000`
6. 前端路由刷新时回退到 `index.html`
7. 流式接口不要被代理缓冲
8. `/media` 路径必须原样透传

可选实现：

- 本机 Nginx
- 本机 Caddy
- 其他反向代理或静态文件服务器

本文不限定你用哪一个，重点是满足上面 8 条。

---

## 8. 本机启动顺序

## 8.1 启动后端

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 8.2 打包前端

```powershell
cd frontend
npm run build
```

## 8.3 启动本机统一入口 `8080`

要求见上一节。

## 8.4 启动 `frpc`

```powershell
C:\frp\frpc.exe -c C:\frp\frpc.toml
```

---

## 9. 试用人员使用方式

只给试用人员一个地址：

```text
http://<ECS公网IP>:18080
```

对他们的说明只需要保留这些：

1. 只打开这个地址
2. 不需要访问 `/docs`
3. 不需要访问任何单独后端端口
4. 同源部署时保持 `backendUrl` 为空；只有跨 origin 部署时再填写后端地址
5. 如果当前仍是 HTTP，不要在前端填写真实第三方 API Key

也就是说，对试用人员来说，后端应该是“无感”的。

---

## 10. 验收标准

## 10.1 基础链路

- `frpc` 已成功连接 `frps`
- ECS 已放行 `7000` 和 `18080`
- `http://<ECS公网IP>:18080` 能打开首页
- `http://<ECS公网IP>:18080/health` 能返回正常

## 10.2 入口一致性

- 试用人员只需要知道一个入口
- 浏览器请求不应跳到 `http://localhost:8000/...`
- 不要求试用人员直接访问 `18000`、`15173` 或 `/docs`
- 设置页里“留空时使用当前站点同源地址”的提示应与部署方式一致
- 视频、图片、音频等媒体请求都走统一入口后的同源链路

## 10.3 真实功能可用性

- 服务端 `.env` 已准备好所需 LLM / 图片 / 视频凭证
- 视频页未误进入前端 Mock 流程
- 角色图可正常加载
- 图片生成可返回 `/media/...`
- 视频生成可返回 `/media/...`
- 视频播放与媒体预览可正常加载

---

## 11. 一旦出现这些现象，优先排查哪里

| 现象 | 优先排查 |
|------|---------|
| 首页能开，但角色图加载失败 | 如果是跨 origin 部署，检查 `backendUrl` 是否填写正确；同时检查 `/media` 是否被统一入口原样透传 |
| 视频页能进，但生成/轮询失败 | Mock 模式、`backendUrl`（仅跨 origin 时）、统一入口代理规则 |
| 浏览器报跨域错误 | 是否误回到了分端口访问 |
| 媒体地址能返回但播放器不工作 | `/media` 是否被错误重写 |
| 换浏览器后突然不正常 | `backendUrl` 是浏览器本地设置，需重新检查 |
| 页面看起来像模拟数据 | `useMock` 是否仍为真 |

---

## 12. 最终结论

最适合当前目标的文档口径应当只有一句话：

**通过阿里云 ECS + FRP 暴露一个统一前端入口 `http://<ECS公网IP>:18080`，由本机 `8080` 同源承接前端页面、API、健康检查和媒体资源，试用人员只操作前端，后端不作为独立访问入口暴露。**

如果后续目标升级为：

- 所有部署都不需要手动填 `backendUrl`
- 不受 Mock 逻辑影响
- 用户可安全填写自己的真实第三方 Key
- 长期稳定对外开放

那就不再是文档重写问题，而是代码修复和正式部署问题。

---

## 13. 参考资料

- FRP 官方 README：<https://github.com/fatedier/frp>
- Alibaba Cloud ECS 安全组文档：<https://www.alibabacloud.com/help/en/ecs/user-guide/manage-ecs-instances-in-security-groups>
- Alibaba Cloud ECS IP 地址文档：<https://www.alibabacloud.com/help/en/ecs/user-guide/ip-address/>
- Alibaba Cloud EIP 快速开始：<https://www.alibabacloud.com/help/en/eip/getting-started>
