<template>
  <div class="page">
    <div class="header">
      <button class="back-btn" @click="router.back()">← 返回</button>
      <h1>API 设置</h1>
    </div>

    <div class="content">
      <div class="mode-banner" :class="store.useMock ? 'mock' : 'live'">
        <span class="mode-dot" />
        {{ store.useMock ? 'Mock 模式：使用预设数据，无需 API Key' : '真实模式：调用 API 接口' }}
      </div>

      <div class="card">
        <!-- 后端服务 -->
        <div class="section-title">后端服务</div>
        <div class="field">
          <label>后端地址</label>
          <div class="input-row">
            <input v-model="backendUrl" placeholder="留空使用默认 http://localhost:8000" />
            <button class="test-btn" @click="testBackend" :disabled="testing">
              {{ backendStatus === 'ok' ? '✓' : backendStatus === 'fail' ? '✗' : testing ? '…' : '测试' }}
            </button>
          </div>
          <span class="hint">FastAPI 服务地址，留空走 Vite 代理</span>
          <span v-if="backendStatus === 'ok'" class="status-ok">连接正常</span>
          <span v-if="backendStatus === 'fail'" class="status-fail">{{ backendError }}</span>
        </div>

        <div class="divider" />

        <!-- 全局默认 -->
        <div class="section-title">全局默认 API <span class="required-badge">必填</span></div>
        <div class="hint-block">未启用专用配置时，文本 / 图片 / 视频均继承此处设置。</div>
        <div class="field">
          <label>服务商</label>
          <select v-model="provider" @change="onProviderChange" class="select-input">
            <option v-for="p in PROVIDERS" :key="p.id" :value="p.id">{{ p.label }}</option>
          </select>
        </div>
        <div class="field">
          <label>Base URL</label>
          <input v-model="llmBaseUrl" placeholder="https://api.example.com/v1" />
          <span class="hint">选择服务商后自动填入，可手动修改</span>
        </div>
        <div class="field">
          <label>API Key</label>
          <div class="input-row">
            <input v-model="apiKey" :type="showKey ? 'text' : 'password'" placeholder="sk-..." />
            <button class="toggle-btn" @click="showKey = !showKey">{{ showKey ? '隐藏' : '显示' }}</button>
          </div>
          <span class="hint">密钥仅保存在本地浏览器中</span>
        </div>

        <div class="divider" />

        <!-- 文本生成专用 -->
        <div class="specialized-header" @click="textEnabled = !textEnabled">
          <div class="specialized-title-group">
            <div class="section-title" style="margin-bottom:0">文本生成专用</div>
            <span class="inherit-label" :class="{ active: textEnabled }">
              {{ textEnabled ? '专用配置已启用' : '继承全局配置' }}
            </span>
          </div>
          <div class="toggle-wrap" @click.stop>
            <label class="toggle">
              <input type="checkbox" v-model="textEnabled" />
              <span class="slider"></span>
            </label>
          </div>
        </div>
        <div v-if="textEnabled" class="specialized-body">
          <div class="field">
            <label>服务商（可选）</label>
            <select v-model="textProvider" @change="onTextProviderChange" class="select-input">
              <option value="">— 继承全局 —</option>
              <option v-for="p in PROVIDERS" :key="p.id" :value="p.id">{{ p.label }}</option>
            </select>
          </div>
          <div class="field">
            <label>Base URL</label>
            <input v-model="textBaseUrl" placeholder="留空继承全局 Base URL" />
          </div>
          <div class="field">
            <label>API Key</label>
            <div class="input-row">
              <input v-model="textApiKey" :type="showTextKey ? 'text' : 'password'" placeholder="留空继承全局 Key" />
              <button class="toggle-btn" @click="showTextKey = !showTextKey">{{ showTextKey ? '隐藏' : '显示' }}</button>
            </div>
          </div>
          <div class="field">
            <label>指定模型（可选）</label>
            <input v-model="textModel" placeholder="留空使用服务商默认，如 claude-3-5-sonnet-latest" />
          </div>
        </div>

        <div class="divider" />

        <!-- 图片生成专用 -->
        <div class="specialized-header" @click="imageEnabled = !imageEnabled">
          <div class="specialized-title-group">
            <div class="section-title" style="margin-bottom:0">图片生成专用</div>
            <span class="inherit-label" :class="{ active: imageEnabled }">
              {{ imageEnabled ? '专用配置已启用' : '继承全局配置' }}
            </span>
          </div>
          <div class="toggle-wrap" @click.stop>
            <label class="toggle">
              <input type="checkbox" v-model="imageEnabled" />
              <span class="slider"></span>
            </label>
          </div>
        </div>
        <div v-if="imageEnabled" class="specialized-body">
          <div class="field">
            <label>Base URL</label>
            <input v-model="imageBaseUrl" placeholder="留空继承全局，如 https://api.siliconflow.cn/v1" />
            <span class="hint">兼容 OpenAI 图片接口（/images/generations）的服务均可使用</span>
          </div>
          <div class="field">
            <label>API Key</label>
            <div class="input-row">
              <input v-model="imageApiKey" :type="showImageKey ? 'text' : 'password'" placeholder="留空继承全局 Key" />
              <button class="toggle-btn" @click="showImageKey = !showImageKey">{{ showImageKey ? '隐藏' : '显示' }}</button>
            </div>
          </div>
          <div class="field">
            <label>指定模型（可选）</label>
            <input v-model="imageModel" placeholder="如 black-forest-labs/FLUX.1-schnell" />
          </div>
        </div>

        <div class="divider" />

        <!-- 视频生成专用 -->
        <div class="specialized-header" @click="videoEnabled = !videoEnabled">
          <div class="specialized-title-group">
            <div class="section-title" style="margin-bottom:0">视频生成专用</div>
            <span class="inherit-label" :class="{ active: videoEnabled }">
              {{ videoEnabled ? '专用配置已启用' : '继承全局配置' }}
            </span>
          </div>
          <div class="toggle-wrap" @click.stop>
            <label class="toggle">
              <input type="checkbox" v-model="videoEnabled" />
              <span class="slider"></span>
            </label>
          </div>
        </div>
        <div v-if="videoEnabled" class="specialized-body">
          <div class="field">
            <label>Base URL</label>
            <input v-model="videoBaseUrl" placeholder="留空继承全局，如 https://dashscope.aliyuncs.com/api/v1" />
            <span class="hint">DashScope 图生视频接口地址（/services/aigc/image2video/video-synthesis）</span>
          </div>
          <div class="field">
            <label>API Key</label>
            <div class="input-row">
              <input v-model="videoApiKey" :type="showVideoKey ? 'text' : 'password'" placeholder="留空继承全局 Key" />
              <button class="toggle-btn" @click="showVideoKey = !showVideoKey">{{ showVideoKey ? '隐藏' : '显示' }}</button>
            </div>
          </div>
          <div class="field">
            <label>指定模型（可选）</label>
            <input v-model="videoModel" placeholder="如 wan2.6-i2v-flash" />
          </div>
        </div>

        <div class="btn-row">
          <button class="save-btn" @click="save">保存设置</button>
        </div>
        <div v-if="saved" class="saved-tip">已保存 ✓</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useSettingsStore, PROVIDERS } from '../stores/settings.js'

const router = useRouter()
const store = useSettingsStore()

// 后端
const backendUrl = ref(store.backendUrl)
const testing = ref(false)
const backendStatus = ref('')
const backendError = ref('')

// 全局
const provider = ref(store.provider)
const llmBaseUrl = ref(store.llmBaseUrl || PROVIDERS.find(p => p.id === store.provider)?.baseUrl || '')
const apiKey = ref(store.apiKey)
const showKey = ref(false)

// 文本专用
const textEnabled = ref(store.textEnabled)
const textProvider = ref(store.textProvider)
const textBaseUrl = ref(store.textBaseUrl)
const textApiKey = ref(store.textApiKey)
const textModel = ref(store.textModel)
const showTextKey = ref(false)

// 图片专用
const imageEnabled = ref(store.imageEnabled)
const imageApiKey = ref(store.imageApiKey)
const imageBaseUrl = ref(store.imageBaseUrl)
const imageModel = ref(store.imageModel)
const showImageKey = ref(false)

// 视频专用
const videoEnabled = ref(store.videoEnabled)
const videoApiKey = ref(store.videoApiKey)
const videoBaseUrl = ref(store.videoBaseUrl)
const videoModel = ref(store.videoModel)
const showVideoKey = ref(false)

const saved = ref(false)

function onProviderChange() {
  const p = PROVIDERS.find(p => p.id === provider.value)
  if (p && p.id !== 'custom') llmBaseUrl.value = p.baseUrl
}

function onTextProviderChange() {
  if (!textProvider.value) { textBaseUrl.value = ''; return }
  const p = PROVIDERS.find(p => p.id === textProvider.value)
  if (p && p.id !== 'custom') textBaseUrl.value = p.baseUrl
}

async function testBackend() {
  testing.value = true
  backendStatus.value = ''
  backendError.value = ''
  try {
    const base = backendUrl.value ? backendUrl.value.replace(/\/$/, '') : ''
    const res = await fetch(`${base}/health`, { signal: AbortSignal.timeout(5000) })
    backendStatus.value = res.ok ? 'ok' : 'fail'
    if (!res.ok) backendError.value = `服务器返回 ${res.status}`
  } catch {
    backendStatus.value = 'fail'
    backendError.value = '无法连接，请检查后端是否启动'
  } finally {
    testing.value = false
  }
}

function save() {
  store.save({
    backendUrl: backendUrl.value,
    provider: provider.value,
    apiKey: apiKey.value,
    llmBaseUrl: llmBaseUrl.value,
    textEnabled: textEnabled.value,
    textProvider: textProvider.value,
    textApiKey: textApiKey.value,
    textBaseUrl: textBaseUrl.value,
    textModel: textModel.value,
    imageEnabled: imageEnabled.value,
    imageApiKey: imageApiKey.value,
    imageBaseUrl: imageBaseUrl.value,
    imageModel: imageModel.value,
    videoEnabled: videoEnabled.value,
    videoApiKey: videoApiKey.value,
    videoBaseUrl: videoBaseUrl.value,
    videoModel: videoModel.value,
  })
  saved.value = true
  setTimeout(() => { saved.value = false }, 2000)
}
</script>

<style scoped>
.page { min-height: 100vh; background: #f5f5f7; padding: 32px 16px; }
.header { max-width: 600px; margin: 0 auto 16px; display: flex; align-items: center; gap: 16px; }
.back-btn {
  padding: 6px 14px; background: #fff; color: #6c63ff;
  border: 1.5px solid #6c63ff; border-radius: 8px;
  font-size: 13px; font-weight: 600; cursor: pointer;
}
.back-btn:hover { background: #f0eeff; }
h1 { font-size: 22px; font-weight: 700; margin: 0; }
.content { max-width: 600px; margin: 0 auto; }

.mode-banner {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; border-radius: 10px;
  font-size: 13px; font-weight: 500; margin-bottom: 16px;
}
.mode-banner.mock { background: #fff8e1; color: #f59e0b; }
.mode-banner.live { background: #e8f5e9; color: #4caf50; }
.mode-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; background: currentColor; }

.card { background: #fff; border-radius: 16px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.section-title { font-size: 12px; font-weight: 700; color: #a78bfa; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 12px; }
.required-badge {
  display: inline-block; margin-left: 8px;
  background: #fee2e2; color: #e53935;
  font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 4px;
  text-transform: none; letter-spacing: 0;
}
.hint-block { font-size: 12px; color: #aaa; margin-bottom: 14px; margin-top: -8px; }
.divider { border: none; border-top: 1px solid #f0eeff; margin: 20px 0; }
.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 16px; }
label { font-size: 13px; font-weight: 600; color: #444; }

.input-row { display: flex; gap: 8px; }
.input-row input { flex: 1; }

.select-input {
  padding: 10px 14px; border: 1.5px solid #e0e0e0; border-radius: 10px;
  font-size: 14px; background: #fff; outline: none; cursor: pointer; transition: border-color 0.2s;
}
.select-input:focus { border-color: #6c63ff; }
input {
  padding: 10px 14px; border: 1.5px solid #e0e0e0; border-radius: 10px;
  font-size: 14px; outline: none; transition: border-color 0.2s; width: 100%; box-sizing: border-box;
}
input:focus { border-color: #6c63ff; }
.hint { font-size: 12px; color: #aaa; }
.status-ok { font-size: 12px; color: #4caf50; font-weight: 600; }
.status-fail { font-size: 12px; color: #e53935; }

.test-btn, .toggle-btn {
  padding: 0 14px; border: 1.5px solid #e0e0e0; border-radius: 10px;
  font-size: 13px; background: #fff; color: #555; cursor: pointer;
  white-space: nowrap; transition: all 0.2s; flex-shrink: 0;
}
.test-btn:hover:not(:disabled), .toggle-btn:hover { border-color: #6c63ff; color: #6c63ff; }
.test-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* Specialized sections */
.specialized-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 14px; border-radius: 10px; cursor: pointer; user-select: none;
  border: 1.5px solid #e0e0e0; transition: border-color 0.2s, background 0.2s;
}
.specialized-header:hover { border-color: #a78bfa; background: #faf8ff; }
.specialized-title-group { display: flex; flex-direction: column; gap: 3px; }
.inherit-label { font-size: 12px; color: #aaa; }
.inherit-label.active { color: #6c63ff; font-weight: 600; }
.toggle-wrap { flex-shrink: 0; }

/* Toggle switch */
.toggle { position: relative; display: inline-block; width: 42px; height: 24px; }
.toggle input { opacity: 0; width: 0; height: 0; }
.slider {
  position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
  background: #ddd; border-radius: 24px; transition: 0.2s;
}
.slider::before {
  position: absolute; content: ''; height: 18px; width: 18px;
  left: 3px; bottom: 3px; background: #fff; border-radius: 50%; transition: 0.2s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}
input:checked + .slider { background: #6c63ff; }
input:checked + .slider::before { transform: translateX(18px); }

.specialized-body {
  border: 1.5px solid #e0e0e0; border-top: none;
  border-radius: 0 0 10px 10px; padding: 16px 14px 4px;
  margin-bottom: 0; background: #faf8ff;
}

.btn-row { display: flex; gap: 10px; margin-top: 20px; }
.save-btn {
  flex: 1; padding: 12px;
  background: linear-gradient(135deg, #6c63ff, #a78bfa);
  color: #fff; border-radius: 12px; font-size: 15px;
  font-weight: 600; transition: opacity 0.2s; cursor: pointer;
}
.save-btn:hover { opacity: 0.9; }
.saved-tip { text-align: center; margin-top: 12px; color: #4caf50; font-size: 14px; font-weight: 600; }
</style>
