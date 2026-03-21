import { defineStore } from 'pinia'

const PROVIDERS = [
  { id: 'siliconflow', label: 'SiliconFlow', baseUrl: 'https://api.siliconflow.cn/v1' },
  { id: 'claude', label: 'Anthropic Claude', baseUrl: 'https://api.anthropic.com' },
  { id: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1' },
  { id: 'qwen', label: '阿里云 Qwen', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { id: 'zhipu', label: '智谱 GLM', baseUrl: 'https://open.bigmodel.cn/api/paas/v4/' },
  { id: 'gemini', label: 'Google Gemini', baseUrl: 'https://generativelanguage.googleapis.com/v1beta' },
  { id: 'custom', label: '自定义', baseUrl: '' },
]

export { PROVIDERS }

const ls = (key, fallback = '') => localStorage.getItem(key) ?? fallback

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    backendUrl: ls('backendUrl'),

    // 全局默认（必须填写）
    provider: ls('provider', 'claude'),
    apiKey: ls('apiKey'),
    llmBaseUrl: ls('llmBaseUrl'),

    // 文本生成专用（开关 + Key / Base URL / 模型）
    textEnabled: ls('textEnabled') === 'true',
    textProvider: ls('textProvider'),
    textApiKey: ls('textApiKey'),
    textBaseUrl: ls('textBaseUrl'),
    textModel: ls('textModel'),

    // 图片生成专用（开关 + Key / Base URL / 模型）
    imageEnabled: ls('imageEnabled') === 'true',
    imageApiKey: ls('imageApiKey'),
    imageBaseUrl: ls('imageBaseUrl'),
    imageModel: ls('imageModel'),

    // 视频生成专用（开关 + Key / Base URL / 模型）
    videoEnabled: ls('videoEnabled') === 'true',
    videoApiKey: ls('videoApiKey'),
    videoBaseUrl: ls('videoBaseUrl'),
    videoModel: ls('videoModel'),
  }),

  getters: {
    // Mock 模式：全局 Key 和文本专用 Key 都未设置
    useMock: (state) => !state.apiKey && !(state.textEnabled && state.textApiKey),

    // 文本生成：专用 > 全局
    effectiveLlmProvider: (state) => (state.textEnabled && state.textProvider) ? state.textProvider : state.provider,
    effectiveLlmBaseUrl:  (state) => (state.textEnabled && state.textBaseUrl)  ? state.textBaseUrl  : state.llmBaseUrl,
    effectiveLlmApiKey:   (state) => (state.textEnabled && state.textApiKey)   ? state.textApiKey   : state.apiKey,

    // 图片生成：未启用专用配置时全部返回空，让后端读 .env SiliconFlow 默认
    effectiveImageApiKey:   (state) => (state.imageEnabled && state.imageApiKey)   ? state.imageApiKey   : '',
    effectiveImageBaseUrl:  (state) => (state.imageEnabled && state.imageBaseUrl)  ? state.imageBaseUrl  : '',
    effectiveImageModel:    (state) => state.imageEnabled ? state.imageModel : '',

    // 视频生成：未启用专用配置时全部返回空，让后端读 .env DashScope 默认
    effectiveVideoApiKey:   (state) => (state.videoEnabled && state.videoApiKey)   ? state.videoApiKey   : '',
    effectiveVideoBaseUrl:  (state) => (state.videoEnabled && state.videoBaseUrl)  ? state.videoBaseUrl  : '',
    effectiveVideoModel:    (state) => state.videoEnabled ? state.videoModel : '',
  },

  actions: {
    save(data) {
      const KEYS = [
        'backendUrl', 'provider', 'apiKey', 'llmBaseUrl',
        'textEnabled', 'textProvider', 'textApiKey', 'textBaseUrl', 'textModel',
        'imageEnabled', 'imageApiKey', 'imageBaseUrl', 'imageModel',
        'videoEnabled', 'videoApiKey', 'videoBaseUrl', 'videoModel',
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
