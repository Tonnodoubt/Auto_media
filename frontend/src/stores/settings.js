import { defineStore } from 'pinia'

// === 发布时改为 false 以完全禁用 Mock 模式 ===
const MOCK_ENABLED = true

export const LLM_PROVIDERS = [
  {
    id: 'claude', label: 'Anthropic Claude',
    baseUrl: 'https://api.anthropic.com',
    models: [
      { id: 'claude-opus-4-6',           label: 'Claude Opus 4.6' },
      { id: 'claude-sonnet-4-6',         label: 'Claude Sonnet 4.6' },
      { id: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5' },
      { id: 'claude-3-5-sonnet-latest',  label: 'Claude 3.5 Sonnet' },
      { id: 'claude-3-5-haiku-latest',   label: 'Claude 3.5 Haiku' },
      { id: 'custom', label: '自定义...' },
    ],
  },
  {
    id: 'openai', label: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    models: [
      { id: 'gpt-4o',      label: 'GPT-4o' },
      { id: 'gpt-4o-mini', label: 'GPT-4o mini' },
      { id: 'o1',          label: 'o1' },
      { id: 'o1-mini',     label: 'o1-mini' },
      { id: 'custom', label: '自定义...' },
    ],
  },
  {
    id: 'siliconflow', label: 'SiliconFlow',
    baseUrl: 'https://api.siliconflow.cn/v1',
    models: [
      { id: 'deepseek-ai/DeepSeek-V3',   label: 'DeepSeek V3' },
      { id: 'deepseek-ai/DeepSeek-R1',   label: 'DeepSeek R1' },
      { id: 'Qwen/Qwen2.5-72B-Instruct', label: 'Qwen2.5 72B' },
      { id: 'Qwen/Qwen2.5-7B-Instruct',  label: 'Qwen2.5 7B' },
      { id: 'THUDM/glm-4-9b-chat',       label: 'GLM-4 9B' },
      { id: 'custom', label: '自定义...' },
    ],
  },
  {
    id: 'qwen', label: '阿里云 Qwen',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    models: [
      { id: 'qwen-max',   label: 'Qwen Max' },
      { id: 'qwen-plus',  label: 'Qwen Plus' },
      { id: 'qwen-turbo', label: 'Qwen Turbo' },
      { id: 'qwen-long',  label: 'Qwen Long' },
      { id: 'custom', label: '自定义...' },
    ],
  },
  {
    id: 'zhipu', label: '智谱 GLM',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4/',
    models: [
      { id: 'glm-4-plus',  label: 'GLM-4 Plus' },
      { id: 'glm-4-air',   label: 'GLM-4 Air' },
      { id: 'glm-4-flash', label: 'GLM-4 Flash' },
      { id: 'custom', label: '自定义...' },
    ],
  },
  {
    id: 'gemini', label: 'Google Gemini',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai/',
    models: [
      { id: 'gemini-2.0-flash',      label: 'Gemini 2.0 Flash' },
      { id: 'gemini-2.0-flash-lite', label: 'Gemini 2.0 Flash Lite' },
      { id: 'gemini-1.5-pro',        label: 'Gemini 1.5 Pro' },
      { id: 'gemini-1.5-flash',      label: 'Gemini 1.5 Flash' },
      { id: 'custom', label: '自定义...' },
    ],
  },
  {
    id: 'custom', label: '自定义',
    baseUrl: '',
    models: [{ id: 'custom', label: '自定义...' }],
  },
]

export const IMAGE_PROVIDERS = [
  {
    id: 'siliconflow', label: 'SiliconFlow',
    baseUrl: 'https://api.siliconflow.cn/v1',
    models: [
      { id: 'black-forest-labs/FLUX.1-schnell',             label: 'FLUX.1 Schnell（免费·快）' },
      { id: 'black-forest-labs/FLUX.1-dev',                 label: 'FLUX.1 Dev' },
      { id: 'black-forest-labs/FLUX.1-pro',                 label: 'FLUX.1 Pro（旗舰）' },
      { id: 'Pro/black-forest-labs/FLUX.1-schnell',         label: 'FLUX.1 Schnell Pro' },
      { id: 'Pro/black-forest-labs/FLUX.1-dev',             label: 'FLUX.1 Dev Pro' },
      { id: 'stabilityai/stable-diffusion-3-5-large',       label: 'SD 3.5 Large' },
      { id: 'stabilityai/stable-diffusion-3-5-large-turbo', label: 'SD 3.5 Large Turbo' },
      { id: 'stabilityai/stable-diffusion-3-medium',        label: 'SD 3 Medium' },
      { id: 'Kwai-Kolors/Kolors',                           label: 'Kolors' },
      { id: 'HiDream-ai/HiDream-I1-Full',                   label: 'HiDream I1 Full' },
      { id: 'HiDream-ai/HiDream-I1-Dev',                    label: 'HiDream I1 Dev' },
      { id: 'Ideogram-AI/Ideogram-V2',                      label: 'Ideogram V2' },
      { id: 'custom', label: '自定义...' },
    ],
  },
  {
    id: 'custom', label: '自定义',
    baseUrl: '',
    models: [{ id: 'custom', label: '自定义...' }],
  },
]

export const VIDEO_PROVIDERS = [
  {
    id: 'dashscope', label: '阿里云 DashScope',
    baseUrl: 'https://dashscope.aliyuncs.com/api/v1',
    models: [
      { id: 'wan2.6-i2v-plus',  label: 'Wan2.6 I2V Plus（质量高）' },
      { id: 'wan2.6-i2v-flash', label: 'Wan2.6 I2V Flash（快）' },
      { id: 'wan2.1-i2v-plus',  label: 'Wan2.1 I2V Plus' },
      { id: 'wan2.1-i2v-turbo', label: 'Wan2.1 I2V Turbo' },
      { id: 'custom', label: '自定义...' },
    ],
  },
  {
    id: 'kling', label: '快手可灵 Kling',
    baseUrl: 'https://api.klingai.com',
    models: [
      { id: 'kling-v2-master',   label: 'Kling v2 Master（最强）' },
      { id: 'kling-v1-5-pro',    label: 'Kling v1.5 Pro' },
      { id: 'kling-v1-pro',      label: 'Kling v1 Pro' },
      { id: 'kling-v1-standard', label: 'Kling v1 Standard' },
      { id: 'custom', label: '自定义...' },
    ],
  },
  {
    id: 'custom', label: '自定义',
    baseUrl: '',
    models: [{ id: 'custom', label: '自定义...' }],
  },
]

function migrateV1() {
  const oldKey = localStorage.getItem('apiKey')
  if (oldKey && !localStorage.getItem('llmApiKey')) {
    localStorage.setItem('llmApiKey', oldKey)
    localStorage.setItem('llmProvider', localStorage.getItem('provider') || 'claude')
    ;['apiKey', 'provider', 'textEnabled', 'textProvider', 'textApiKey', 'textBaseUrl', 'textModel',
      'imageEnabled', 'videoEnabled'].forEach(k => localStorage.removeItem(k))
  }
}
migrateV1()

const ls = (key, fallback = '') => localStorage.getItem(key) ?? fallback

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    backendUrl:    ls('backendUrl'),
    llmProvider:   ls('llmProvider', 'claude'),
    llmApiKey:     ls('llmApiKey'),
    llmBaseUrl:    ls('llmBaseUrl'),
    llmModel:      ls('llmModel'),
    imageProvider: ls('imageProvider', 'siliconflow'),
    imageApiKey:   ls('imageApiKey'),
    imageBaseUrl:  ls('imageBaseUrl'),
    imageModel:    ls('imageModel'),
    videoProvider: ls('videoProvider', 'dashscope'),
    videoApiKey:   ls('videoApiKey'),
    videoBaseUrl:  ls('videoBaseUrl'),
    videoModel:    ls('videoModel'),
  }),

  getters: {
    useMock: (state) => MOCK_ENABLED && !state.llmApiKey,

    effectiveLlmProvider: (state) => state.llmProvider,
    effectiveLlmBaseUrl:  (state) => state.llmBaseUrl,
    effectiveLlmApiKey:   (state) => state.llmApiKey,
    effectiveLlmModel:    (state) => state.llmModel,

    effectiveImageApiKey:  (state) => state.imageApiKey,
    effectiveImageBaseUrl: (state) => state.imageBaseUrl,
    effectiveImageModel:   (state) => state.imageModel,

    effectiveVideoProvider: (state) => state.videoProvider,
    effectiveVideoApiKey:   (state) => state.videoApiKey,
    effectiveVideoBaseUrl:  (state) => state.videoBaseUrl,
    effectiveVideoModel:    (state) => state.videoModel,
  },

  actions: {
    save(data) {
      const KEYS = [
        'backendUrl',
        'llmProvider', 'llmApiKey', 'llmBaseUrl', 'llmModel',
        'imageProvider', 'imageApiKey', 'imageBaseUrl', 'imageModel',
        'videoProvider', 'videoApiKey', 'videoBaseUrl', 'videoModel',
      ]
      for (const key of KEYS) {
        if (key in data) {
          this[key] = data[key]
          localStorage.setItem(key, String(data[key]))
        }
      }
    },
  },
})
