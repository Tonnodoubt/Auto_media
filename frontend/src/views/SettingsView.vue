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

      <!-- 后端服务 -->
      <div class="card card-backend">
        <div class="section-header">
          <span class="section-icon">⚙️</span>
          <span class="section-title">后端服务</span>
        </div>
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
      </div>

      <!-- 文本生成 -->
      <div class="card card-llm">
        <div class="section-header">
          <span class="section-icon">💬</span>
          <span class="section-title">文本生成（LLM）</span>
        </div>
        <div class="field">
          <label>服务商</label>
          <select v-model="llmProvider" @change="onLlmProviderChange" class="select-input">
            <option v-for="p in LLM_PROVIDERS" :key="p.id" :value="p.id">{{ p.label }}</option>
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
            <input v-model="llmApiKey" :type="showLlmKey ? 'text' : 'password'" placeholder="sk-..." />
            <button class="toggle-btn" @click="showLlmKey = !showLlmKey">{{ showLlmKey ? '隐藏' : '显示' }}</button>
          </div>
          <span class="hint">密钥仅保存在本地浏览器中</span>
        </div>
        <div class="field">
          <label>模型</label>
          <select v-model="llmModelSelect" class="select-input">
            <option v-for="m in currentLlmModels" :key="m.id" :value="m.id">{{ m.label }}</option>
          </select>
          <input
            v-if="llmModelSelect === 'custom'"
            v-model="llmModelCustom"
            placeholder="输入模型名称，如 claude-3-5-sonnet-latest"
            style="margin-top:6px"
          />
        </div>

        <!-- 高级选项 -->
        <div class="advanced-toggle" @click="showAdvanced = !showAdvanced">
          <span class="advanced-arrow" :class="{ open: showAdvanced }">▶</span>
          高级选项
        </div>
        <div v-if="showAdvanced" class="advanced-section">
          <div class="adv-row">
            <span id="use-script-model-label" class="adv-label">分镜专用配置</span>
            <label class="toggle-switch">
              <input type="checkbox" v-model="useScriptModel" @change="onScriptModelToggle" aria-labelledby="use-script-model-label" />
              <span class="toggle-track" />
            </label>
          </div>
          <span class="hint">启用后，分镜生成步骤将使用下方独立配置（服务商 / API Key / 模型），其余步骤仍使用上方默认 LLM 配置。</span>
          <template v-if="useScriptModel">
            <div class="field" style="margin-top:12px; margin-bottom:0">
              <label for="script-provider">服务商</label>
              <select id="script-provider" v-model="scriptProvider" @change="onScriptProviderChange" class="select-input">
                <option v-for="p in LLM_PROVIDERS" :key="p.id" :value="p.id">{{ p.label }}</option>
              </select>
            </div>
            <div class="field" style="margin-bottom:0">
              <label for="script-base-url">Base URL</label>
              <input id="script-base-url" v-model="scriptBaseUrl" placeholder="https://api.example.com/v1" />
            </div>
            <div class="field" style="margin-bottom:0">
              <label for="script-api-key">API Key</label>
              <div class="input-row">
                <input id="script-api-key" v-model="scriptApiKey" :type="showScriptKey ? 'text' : 'password'" placeholder="sk-..." />
                <button class="toggle-btn" @click="showScriptKey = !showScriptKey">{{ showScriptKey ? '隐藏' : '显示' }}</button>
              </div>
              <span class="hint">密钥仅保存在本地浏览器中</span>
            </div>
            <div class="field" style="margin-bottom:0">
              <label for="script-model-select">模型</label>
              <select id="script-model-select" v-model="scriptModelSelect" class="select-input">
                <option v-for="m in currentScriptModels" :key="m.id" :value="m.id">{{ m.label }}</option>
              </select>
              <input
                v-if="scriptModelSelect === 'custom'"
                id="script-model-custom"
                v-model="scriptModelCustom"
                aria-label="自定义模型名称"
                placeholder="输入模型名称，如 claude-opus-4-6"
                style="margin-top:6px"
              />
            </div>
          </template>
        </div>
      </div>

      <!-- 图片生成 -->
      <div class="card card-image">
        <div class="section-header">
          <span class="section-icon">🖼️</span>
          <span class="section-title">图片生成</span>
        </div>
        <div class="field">
          <label>服务商</label>
          <select v-model="imageProvider" @change="onImageProviderChange" class="select-input">
            <option v-for="p in IMAGE_PROVIDERS" :key="p.id" :value="p.id">{{ p.label }}</option>
          </select>
        </div>
        <div class="field">
          <label>Base URL</label>
          <input v-model="imageBaseUrl" placeholder="https://api.siliconflow.cn/v1" />
          <span class="hint">兼容 OpenAI /images/generations 接口的服务均可使用</span>
        </div>
        <div class="field">
          <label>API Key</label>
          <div class="input-row">
            <input v-model="imageApiKey" :type="showImageKey ? 'text' : 'password'" placeholder="sk-..." />
            <button class="toggle-btn" @click="showImageKey = !showImageKey">{{ showImageKey ? '隐藏' : '显示' }}</button>
          </div>
          <span class="hint">密钥仅保存在本地浏览器中</span>
        </div>
        <div class="field">
          <label>模型</label>
          <select v-if="!(currentImageModels.length === 1 && currentImageModels[0].id === 'custom')" v-model="imageModelSelect" class="select-input">
            <option v-for="m in currentImageModels" :key="m.id" :value="m.id">{{ m.label }}</option>
          </select>
          <input
            v-if="imageModelSelect === 'custom'"
            v-model="imageModelCustom"
            :placeholder="imageProvider === 'doubao' ? '输入端点 ID，如 ep-xxxxxxxx' : '输入模型名称，如 black-forest-labs/FLUX.1-schnell'"
            style="margin-top:6px"
          />
        </div>
      </div>

      <!-- 视频生成 -->
      <div class="card card-video">
        <div class="section-header">
          <span class="section-icon">🎬</span>
          <span class="section-title">视频生成</span>
        </div>
        <div class="field">
          <label>服务商</label>
          <select v-model="videoProvider" @change="onVideoProviderChange" class="select-input">
            <option v-for="p in VIDEO_PROVIDERS" :key="p.id" :value="p.id">{{ p.label }}</option>
          </select>
        </div>
        <div class="field">
          <label>Base URL</label>
          <input v-model="videoBaseUrl" placeholder="https://dashscope.aliyuncs.com/api/v1" />
          <span class="hint">{{ videoProvider === 'kling' ? 'Kling 图生视频接口地址' : 'DashScope 图生视频接口地址' }}</span>
        </div>
        <div class="field">
          <label>API Key</label>
          <div class="input-row">
            <input v-model="videoApiKey" :type="showVideoKey ? 'text' : 'password'" :placeholder="videoProvider === 'kling' ? 'access_key_id:secret_key' : 'sk-...'" />
            <button class="toggle-btn" @click="showVideoKey = !showVideoKey">{{ showVideoKey ? '隐藏' : '显示' }}</button>
          </div>
          <span v-if="videoProvider === 'kling'" class="hint">Kling 格式：access_key_id:secret_key（冒号连接两个字段）</span>
          <span v-else class="hint">密钥仅保存在本地浏览器中</span>
        </div>
        <div class="field">
          <label>模型</label>
          <select v-if="!(currentVideoModels.length === 1 && currentVideoModels[0].id === 'custom')" v-model="videoModelSelect" class="select-input">
            <option v-for="m in currentVideoModels" :key="m.id" :value="m.id">{{ m.label }}</option>
          </select>
          <input
            v-if="videoModelSelect === 'custom'"
            v-model="videoModelCustom"
            :placeholder="videoProvider === 'doubao' ? '输入端点 ID，如 ep-xxxxxxxx' : '输入模型名称，如 wan2.1-i2v-turbo'"
            style="margin-top:6px"
          />
        </div>
      </div>

      <div class="btn-row">
        <button class="save-btn" @click="save">保存设置</button>
      </div>
      <div v-if="saved" class="saved-tip">已保存 ✓</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useSettingsStore, LLM_PROVIDERS, IMAGE_PROVIDERS, VIDEO_PROVIDERS } from '../stores/settings.js'

const router = useRouter()
const store = useSettingsStore()

// 后端
const backendUrl    = ref(store.backendUrl)
const testing       = ref(false)
const backendStatus = ref('')
const backendError  = ref('')

// LLM
const llmProvider = ref(store.llmProvider || 'claude')
const llmBaseUrl  = ref(store.llmBaseUrl  || LLM_PROVIDERS.find(p => p.id === (store.llmProvider || 'claude'))?.baseUrl || '')
const llmApiKey   = ref(store.llmApiKey)
const showLlmKey  = ref(false)

const currentLlmModels = computed(() =>
  LLM_PROVIDERS.find(p => p.id === llmProvider.value)?.models ?? [{ id: 'custom', label: '自定义...' }]
)
const _initLlmModel = () => {
  const stored = store.llmModel
  const isPreset = !!stored && currentLlmModels.value.some(m => m.id !== 'custom' && m.id === stored)
  return { select: isPreset ? stored : (stored ? 'custom' : currentLlmModels.value[0]?.id ?? 'custom'), custom: isPreset ? '' : (stored || '') }
}
const { select: _ls, custom: _lc } = _initLlmModel()
const llmModelSelect = ref(_ls)
const llmModelCustom = ref(_lc)

// 高级选项：脚本生成专用配置
const _hasScript = !!(store.scriptModel || store.scriptApiKey || store.scriptBaseUrl || store.scriptProvider)
const showAdvanced   = ref(_hasScript)
const useScriptModel = ref(_hasScript)
const scriptProvider = ref(store.scriptProvider || store.llmProvider || 'claude')
const scriptBaseUrl  = ref(store.scriptBaseUrl  || LLM_PROVIDERS.find(p => p.id === (store.scriptProvider || store.llmProvider || 'claude'))?.baseUrl || '')
const scriptApiKey   = ref(store.scriptApiKey)
const showScriptKey  = ref(false)

const currentScriptModels = computed(() =>
  LLM_PROVIDERS.find(p => p.id === scriptProvider.value)?.models ?? [{ id: 'custom', label: '自定义...' }]
)
const _initScriptModel = () => {
  const stored = store.scriptModel
  const isPreset = !!stored && currentScriptModels.value.some(m => m.id !== 'custom' && m.id === stored)
  return { select: isPreset ? stored : (stored ? 'custom' : currentScriptModels.value[0]?.id ?? 'custom'), custom: isPreset ? '' : (stored || '') }
}
const { select: _ss, custom: _sc } = _initScriptModel()
const scriptModelSelect = ref(_ss)
const scriptModelCustom = ref(_sc)

function onScriptProviderChange() {
  const p = LLM_PROVIDERS.find(prov => prov.id === scriptProvider.value)
  if (p && p.id !== 'custom') scriptBaseUrl.value = p.baseUrl
  scriptModelSelect.value = currentScriptModels.value[0]?.id ?? 'custom'
  scriptModelCustom.value = ''
}

function onScriptModelToggle() {
  scriptProvider.value    = llmProvider.value
  scriptBaseUrl.value     = llmBaseUrl.value
  scriptApiKey.value      = ''
  scriptModelSelect.value = llmModelSelect.value
  scriptModelCustom.value = llmModelCustom.value
}

// Image
const imageProvider = ref(store.imageProvider || 'siliconflow')
const imageBaseUrl  = ref(store.imageBaseUrl  || IMAGE_PROVIDERS.find(p => p.id === (store.imageProvider || 'siliconflow'))?.baseUrl || '')
const imageApiKey   = ref(store.imageApiKey)
const showImageKey  = ref(false)

const currentImageModels = computed(() =>
  IMAGE_PROVIDERS.find(p => p.id === imageProvider.value)?.models ?? [{ id: 'custom', label: '自定义...' }]
)
const _initImageModel = () => {
  const stored = store.imageModel
  const isPreset = !!stored && currentImageModels.value.some(m => m.id !== 'custom' && m.id === stored)
  return { select: isPreset ? stored : (stored ? 'custom' : currentImageModels.value[0]?.id ?? 'custom'), custom: isPreset ? '' : (stored || '') }
}
const { select: _is, custom: _ic } = _initImageModel()
const imageModelSelect = ref(_is)
const imageModelCustom = ref(_ic)

// Video
const videoProvider = ref(store.videoProvider || 'dashscope')
const videoBaseUrl  = ref(store.videoBaseUrl  || VIDEO_PROVIDERS.find(p => p.id === (store.videoProvider || 'dashscope'))?.baseUrl || '')
const videoApiKey   = ref(store.videoApiKey)
const showVideoKey  = ref(false)

const currentVideoModels = computed(() =>
  VIDEO_PROVIDERS.find(p => p.id === videoProvider.value)?.models ?? [{ id: 'custom', label: '自定义...' }]
)
const _initVideoModel = () => {
  const stored = store.videoModel
  const isPreset = !!stored && currentVideoModels.value.some(m => m.id !== 'custom' && m.id === stored)
  return { select: isPreset ? stored : (stored ? 'custom' : currentVideoModels.value[0]?.id ?? 'custom'), custom: isPreset ? '' : (stored || '') }
}
const { select: _vs, custom: _vc } = _initVideoModel()
const videoModelSelect = ref(_vs)
const videoModelCustom = ref(_vc)

const saved = ref(false)

function onLlmProviderChange() {
  const p = LLM_PROVIDERS.find(p => p.id === llmProvider.value)
  if (p && p.id !== 'custom') llmBaseUrl.value = p.baseUrl
  llmModelSelect.value = currentLlmModels.value[0]?.id ?? 'custom'
  llmModelCustom.value = ''
}

function onImageProviderChange() {
  const p = IMAGE_PROVIDERS.find(p => p.id === imageProvider.value)
  if (p && p.id !== 'custom') imageBaseUrl.value = p.baseUrl
  imageModelSelect.value = currentImageModels.value[0]?.id ?? 'custom'
  imageModelCustom.value = ''
}

function onVideoProviderChange() {
  const p = VIDEO_PROVIDERS.find(p => p.id === videoProvider.value)
  if (p && p.id !== 'custom') videoBaseUrl.value = p.baseUrl
  videoModelSelect.value = currentVideoModels.value[0]?.id ?? 'custom'
  videoModelCustom.value = ''
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

const getModel = (select, custom) => select === 'custom' ? custom : select

function save() {
  const scriptModelValue = useScriptModel.value
    ? getModel(scriptModelSelect.value, scriptModelCustom.value)
    : ''
  store.save({
    backendUrl:     backendUrl.value,
    llmProvider:    llmProvider.value,
    llmApiKey:      llmApiKey.value,
    llmBaseUrl:     llmBaseUrl.value,
    llmModel:       getModel(llmModelSelect.value, llmModelCustom.value),
    scriptModel:    scriptModelValue,
    scriptProvider: useScriptModel.value ? scriptProvider.value : '',
    scriptApiKey:   useScriptModel.value ? scriptApiKey.value   : '',
    scriptBaseUrl:  useScriptModel.value ? scriptBaseUrl.value  : '',
    imageProvider:  imageProvider.value,
    imageApiKey:    imageApiKey.value,
    imageBaseUrl:   imageBaseUrl.value,
    imageModel:     getModel(imageModelSelect.value, imageModelCustom.value),
    videoProvider:  videoProvider.value,
    videoApiKey:    videoApiKey.value,
    videoBaseUrl:   videoBaseUrl.value,
    videoModel:     getModel(videoModelSelect.value, videoModelCustom.value),
  })
  saved.value = true
  setTimeout(() => { saved.value = false }, 2000)
}
</script>

<style scoped>
.page { min-height: 100vh; background: #f0f0f5; padding: 32px 16px; }
.header { max-width: 600px; margin: 0 auto 16px; display: flex; align-items: center; gap: 16px; }
.back-btn {
  padding: 6px 14px; background: #fff; color: #6c63ff;
  border: 1.5px solid #6c63ff; border-radius: 8px;
  font-size: 13px; font-weight: 600; cursor: pointer;
}
.back-btn:hover { background: #f0eeff; }
h1 { font-size: 22px; font-weight: 700; margin: 0; }
.content { max-width: 600px; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; }

.mode-banner {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; border-radius: 10px;
  font-size: 13px; font-weight: 500;
}
.mode-banner.mock { background: #fff8e1; color: #f59e0b; }
.mode-banner.live { background: #e8f5e9; color: #4caf50; }
.mode-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; background: currentColor; }

.card {
  background: #fff; border-radius: 16px; padding: 20px 24px 24px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.07);
  border-left: 4px solid transparent;
}
.card-backend { border-left-color: #94a3b8; }
.card-llm     { border-left-color: #6c63ff; }
.card-image   { border-left-color: #f59e0b; }
.card-video   { border-left-color: #10b981; }

.section-header {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 16px; padding-bottom: 12px;
  border-bottom: 1px solid #f3f4f6;
}
.section-icon { font-size: 16px; line-height: 1; }
.section-title { font-size: 13px; font-weight: 700; color: #374151; letter-spacing: 0.03em; }

.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 16px; }
.field:last-child { margin-bottom: 0; }
label { font-size: 13px; font-weight: 600; color: #555; }

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
.hint-inline { font-size: 11px; color: #bbb; font-weight: 400; }
.status-ok { font-size: 12px; color: #4caf50; font-weight: 600; }
.status-fail { font-size: 12px; color: #e53935; }

.test-btn, .toggle-btn {
  padding: 0 14px; border: 1.5px solid #e0e0e0; border-radius: 10px;
  font-size: 13px; background: #fff; color: #555; cursor: pointer;
  white-space: nowrap; transition: all 0.2s; flex-shrink: 0;
}
.test-btn:hover:not(:disabled), .toggle-btn:hover { border-color: #6c63ff; color: #6c63ff; }
.test-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-row { display: flex; gap: 10px; }
.save-btn {
  flex: 1; padding: 13px;
  background: linear-gradient(135deg, #6c63ff, #a78bfa);
  color: #fff; border-radius: 12px; font-size: 15px;
  font-weight: 600; transition: opacity 0.2s; cursor: pointer;
}
.save-btn:hover { opacity: 0.9; }
.saved-tip { text-align: center; color: #4caf50; font-size: 14px; font-weight: 600; }

/* 高级选项 */
.advanced-toggle {
  display: flex; align-items: center; gap: 6px;
  margin-top: 4px; padding: 6px 0; cursor: pointer;
  font-size: 12px; color: #888; user-select: none;
  border-top: 1px dashed #eee;
}
.advanced-toggle:hover { color: #6c63ff; }
.advanced-arrow { font-size: 10px; transition: transform 0.2s; display: inline-block; }
.advanced-arrow.open { transform: rotate(90deg); }
.advanced-section {
  margin-top: 12px; padding: 14px 16px; background: #f8f7ff;
  border-radius: 10px; border: 1px solid #ede9ff;
  display: flex; flex-direction: column; gap: 8px;
}
.adv-row { display: flex; align-items: center; justify-content: space-between; }
.adv-label { font-size: 13px; font-weight: 600; color: #555; }

/* Toggle switch */
.toggle-switch { position: relative; display: inline-block; width: 38px; height: 22px; flex-shrink: 0; }
.toggle-switch input { opacity: 0; width: 0; height: 0; }
.toggle-track {
  position: absolute; inset: 0; border-radius: 22px;
  background: #d1d5db; cursor: pointer; transition: background 0.2s;
}
.toggle-track::before {
  content: ''; position: absolute;
  width: 16px; height: 16px; left: 3px; bottom: 3px;
  border-radius: 50%; background: #fff; transition: transform 0.2s;
}
.toggle-switch input:checked + .toggle-track { background: #6c63ff; }
.toggle-switch input:checked + .toggle-track::before { transform: translateX(16px); }
.toggle-switch input:focus-visible + .toggle-track { outline: 2px solid #6c63ff; outline-offset: 2px; }
</style>
