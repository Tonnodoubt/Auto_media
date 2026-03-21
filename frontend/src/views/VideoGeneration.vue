<template>
  <div class="page">
    <StepIndicator :current="5" />
    <div class="content">
      <h1>场景分镜</h1>
      <p class="subtitle">选择场景进行分镜解析和视频生成</p>

      <!-- 从 Step4 导入的剧本 -->
      <div v-if="hasStoryData" class="story-import">
        <!-- 标题栏 -->
        <div class="import-header">
          <div class="header-left">
            <span class="import-icon">📖</span>
            <h3>从 Step4 导入的剧本</h3>
          </div>
          <div class="header-right">
            <span class="scene-count">已选择 {{ selectedCount }}/{{ totalScenes }} 个场景</span>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="import-actions">
          <button class="action-btn" @click="selectAll">
            <span>✓</span> 全选
          </button>
          <button class="action-btn" @click="clearSelection">
            <span>✕</span> 清空
          </button>
          <button class="action-btn" @click="showManualInput = true">
            <span>✎</span> 手动输入
          </button>
        </div>

        <!-- 场景卡片列表（参照 SceneStream 样式） -->
        <div class="episode-list">
          <div v-for="ep in storyStore.scenes" :key="ep.episode" class="episode-card">
            <!-- 集标题 -->
            <div class="ep-header" @click="toggleEpisode(ep.episode)">
              <input
                type="checkbox"
                :checked="isEpisodeSelected(ep.episode)"
                :indeterminate.prop="isEpisodeIndeterminate(ep.episode)"
                @click.stop
                @change="toggleEpisode(ep.episode)"
                class="ep-checkbox"
              />
              <span class="ep-badge">第 {{ ep.episode }} 集</span>
              <span class="ep-title">{{ ep.title }}</span>
              <span class="ep-count">{{ getEpisodeSelectedCount(ep.episode) }}/{{ ep.scenes.length }}</span>
            </div>

            <!-- 场景列表 -->
            <div class="scenes">
              <div
                v-for="scene in ep.scenes"
                :key="scene.scene_number"
                class="scene-block"
                :class="{ selected: selectedScenes[ep.episode]?.[scene.scene_number] }"
              >
                <!-- 场景标题和复选框 -->
                <div class="scene-header" @click="toggleScene(ep.episode, scene.scene_number)">
                  <input
                    type="checkbox"
                    :checked="selectedScenes[ep.episode]?.[scene.scene_number]"
                    @click.stop
                    @change="toggleScene(ep.episode, scene.scene_number)"
                    class="scene-checkbox"
                  />
                  <span class="scene-num">场景 {{ String(scene.scene_number).padStart(2, '0') }}</span>
                  <button
                    class="toggle-script-btn"
                    :class="{ expanded: expandedScenes[`${ep.episode}-${scene.scene_number}`] }"
                    @click.stop="toggleScriptVisibility(ep.episode, scene.scene_number)"
                    :title="expandedScenes[`${ep.episode}-${scene.scene_number}`] ? '收起剧本' : '展开剧本'"
                  >
                    ▾
                  </button>
                </div>

                <!-- 场景内容 -->
                <div
                  class="scene-content"
                  :class="{ collapsed: !expandedScenes[`${ep.episode}-${scene.scene_number}`] }"
                >
                  <div class="scene-row">
                    <span class="scene-tag">【环境】</span>
                    <span class="scene-text">{{ scene.environment }}</span>
                  </div>
                  <div class="scene-row">
                    <span class="scene-tag">【画面】</span>
                    <span class="scene-text">{{ scene.visual }}</span>
                  </div>

                  <!-- 台词 -->
                  <div v-if="scene.audio && scene.audio.length > 0" class="audio-lines">
                    <div v-for="(a, i) in scene.audio" :key="i" class="audio-line">
                      <span class="character">{{ a.character }}：</span>
                      <span class="line">{{ a.line }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 空状态：无剧本数据 -->
      <div v-else class="empty-state">
        <div class="empty-icon">📝</div>
        <p class="empty-title">没有检测到剧本数据</p>
        <p class="empty-desc">请先在 Step4 生成剧本，或手动输入剧本内容</p>
        <div class="empty-actions">
          <button class="primary-btn" @click="router.push('/step4')">
            前往 Step4
          </button>
          <button class="secondary-btn" @click="showManualInput = true">
            手动输入
          </button>
        </div>
      </div>

      <!-- 手动输入模态框 -->
      <div v-if="showManualInput" class="modal-overlay" @click.self="showManualInput = false">
        <div class="modal">
          <div class="modal-header">
            <h3>手动输入剧本</h3>
            <button class="close-btn" @click="showManualInput = false">✕</button>
          </div>

          <div class="modal-body">
            <div class="tabs">
              <button class="tab-btn" :class="{ active: manualTab === 'upload' }" @click="manualTab = 'upload'">
                上传文件
              </button>
              <button class="tab-btn" :class="{ active: manualTab === 'paste' }" @click="manualTab = 'paste'">
                粘贴文字
              </button>
            </div>

            <div v-show="manualTab === 'upload'" class="upload-zone">
              <div
                class="upload-area"
                :class="{ 'drag-over': isDragOver }"
                @click="triggerFileInput"
                @dragover.prevent="isDragOver = true"
                @dragleave="isDragOver = false"
                @drop.prevent="handleDrop"
              >
                <svg width="32" height="32" fill="none" stroke="#555" stroke-width="1.5" viewBox="0 0 24 24">
                  <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M12 12V4m0 0L8 8m4-4l4 4"/>
                </svg>
                <p>点击或拖拽上传剧本文件</p>
                <p>支持 .txt / .json</p>
                <input ref="fileInput" type="file" accept=".txt,.json" style="display: none" @change="handleFileSelect">
              </div>
              <textarea
                v-show="uploadedScript"
                v-model="uploadedScript"
                class="script-textarea"
                placeholder="上传的剧本内容..."
              ></textarea>
            </div>

            <div v-show="manualTab === 'paste'">
              <textarea v-model="pastedScript" class="script-textarea" placeholder="粘贴剧本内容..." style="height: 200px"></textarea>
            </div>
          </div>

          <div class="modal-footer">
            <button class="cancel-btn" @click="showManualInput = false">取消</button>
            <button class="confirm-btn" @click="confirmManualInput">确定</button>
          </div>
        </div>
      </div>

      <!-- Controls -->
      <div class="controls">
        <button @click="parseStoryboard" :disabled="isParsing || (manualOverride ? !hasManualScript : (hasStoryData && selectedCount === 0))" class="parse-btn">
          {{ isParsing ? '解析中...' : (manualOverride ? '开始解析分镜' : (hasStoryData ? `开始解析 ${selectedCount} 个场景` : '开始解析分镜')) }}
        </button>
      </div>

      <!-- Progress -->
      <div v-if="progress.show" class="progress-section">
        <div class="progress-label">{{ progress.label }}</div>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: progress.percent + '%' }"></div>
        </div>
      </div>

      <!-- Error -->
      <div v-if="error" class="error-message">
        ❌ {{ error }}
      </div>

      <!-- API Key Modal -->
      <ApiKeyModal
        :show="showKeyModal"
        :type="keyModalType"
        :title="keyModalType === 'invalid' ? 'API Key 错误' : '未设置 API Key'"
        :message="keyModalMsg || '请先前往设置页填入 API Key，才能继续。'"
        @close="showKeyModal = false"
      />

      <!-- Storyboard result -->
      <div v-if="shots.length > 0" class="storyboard">
        <div class="storyboard-header">
          <h2>{{ shots.length }} 个分镜 · 共 {{ totalDuration }} 秒</h2>
          <div class="action-group">
            <select v-model="selectedVoice" class="voice-select">
              <option v-for="voice in voices" :key="voice.id" :value="voice.id">
                {{ voice.name }}
              </option>
            </select>
            <button class="action-btn" @click="generateAllTTS">全部生成语音</button>
            <button class="action-btn" @click="generateAllImages">全部生成图片</button>
            <button class="action-btn" @click="generateAllVideos">全部生成视频</button>
          </div>
        </div>
        <div class="shots-grid">
          <div v-for="shot in shots" :key="shot.shot_id" class="shot-card">
            <div class="shot-header">
              <span class="shot-id">{{ shot.shot_id }}</span>
              <div class="shot-meta">
                <span class="tag type">{{ shot.camera_motion }}</span>
                <span class="tag">{{ shot.estimated_duration }}s</span>
              </div>
            </div>
            <div v-if="shot.dialogue" class="shot-field">
              <label>台词 / 旁白</label>
              <p>{{ shot.dialogue }}</p>
            </div>
            <div class="shot-field">
              <label>画面描述</label>
              <p>{{ shot.visual_description_zh }}</p>
            </div>
            <div class="shot-field">
              <label>Visual Prompt</label>
              <p class="en">{{ shot.visual_prompt }}</p>
            </div>

            <!-- TTS controls -->
            <div v-if="shot.dialogue" class="tts-bar">
              <button class="tts-btn" @click="generateOneTTS(shot.shot_id)" :disabled="shot.ttsLoading">
                {{ shot.ttsLoading ? '生成中...' : '生成语音' }}
              </button>
              <audio v-if="shot.audio_url" :src="getMediaUrl(shot.audio_url)" controls style="height: 28px; flex: 1"></audio>
              <span v-if="shot.audio_duration" class="tts-duration">{{ shot.audio_duration.toFixed(1) }}s</span>
            </div>

            <!-- Image controls -->
            <div class="tts-bar">
              <button class="tts-btn" @click="generateOneImage(shot.shot_id)" :disabled="shot.imageLoading">
                {{ shot.imageLoading ? '生成中...' : '生成图片' }}
              </button>
            </div>
            <img v-if="shot.image_url" :src="getMediaUrl(shot.image_url)" class="shot-image" />
            <div v-if="shot.image_url" class="tts-bar">
              <button class="tts-btn" @click="generateOneImage(shot.shot_id)" :disabled="shot.imageLoading">重新生成图片</button>
              <button class="tts-btn" @click="generateOneVideo(shot.shot_id)" :disabled="shot.videoLoading">
                {{ shot.videoLoading ? '生成中...' : '生成视频' }}
              </button>
            </div>
            <video v-if="shot.video_url" :src="getMediaUrl(shot.video_url)" controls class="shot-video"></video>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSettingsStore } from '../stores/settings.js'
import { useStoryStore } from '../stores/story.js'
import StepIndicator from '../components/StepIndicator.vue'
import ApiKeyModal from '../components/ApiKeyModal.vue'

const router = useRouter()
const settings = useSettingsStore()
const storyStore = useStoryStore()

// 场景选择相关
const selectedScenes = ref({})
const expandedScenes = ref({})
const showManualInput = ref(false)
const manualTab = ref('paste')
const uploadedScript = ref('')
const pastedScript = ref('')
const isDragOver = ref(false)
const fileInput = ref(null)
const manualOverride = ref(false)

// 解析和结果
const isParsing = ref(false)
const error = ref('')
const shots = ref([])
const voices = ref([])
const selectedVoice = ref('')
const showKeyModal = ref(false)
const keyModalType = ref('missing')
const keyModalMsg = ref('')

const progress = ref({
  show: false,
  label: '',
  percent: 0
})

// 生成唯一 ID
function generateUniqueId() {
  return `ui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// 并发限制执行器
const MAX_CONCURRENCY = 3

async function runWithConcurrency(items, fn, concurrency = MAX_CONCURRENCY) {
  const results = []
  for (let i = 0; i < items.length; i += concurrency) {
    const batch = items.slice(i, i + concurrency)
    const batchResults = await Promise.allSettled(batch.map(fn))
    results.push(...batchResults)
  }
  return results
}

// 计算属性
const hasStoryData = computed(() => {
  return storyStore.scenes && storyStore.scenes.length > 0
})

const hasManualScript = computed(() => {
  return !!(pastedScript.value.trim() || uploadedScript.value.trim())
})

const selectedCount = computed(() => {
  let count = 0
  Object.values(selectedScenes.value).forEach(episode => {
    Object.values(episode).forEach(selected => {
      if (selected) count++
    })
  })
  return count
})

const totalScenes = computed(() => {
  if (!storyStore.scenes) return 0
  return storyStore.scenes.reduce((sum, ep) => sum + ep.scenes.length, 0)
})

const totalDuration = computed(() => shots.value.reduce((sum, s) => sum + s.estimated_duration, 0))

// 场景选择相关函数
function initSelectedScenes() {
  storyStore.scenes.forEach(episode => {
    if (!selectedScenes.value[episode.episode]) {
      selectedScenes.value[episode.episode] = {}
    }
    episode.scenes.forEach(scene => {
      if (selectedScenes.value[episode.episode][scene.scene_number] === undefined) {
        selectedScenes.value[episode.episode][scene.scene_number] = false
      }
      // 默认收起所有场景的剧本
      const key = `${episode.episode}-${scene.scene_number}`
      if (expandedScenes.value[key] === undefined) {
        expandedScenes.value[key] = false
      }
    })
  })
}

function toggleScene(episodeNum, sceneNum) {
  selectedScenes.value[episodeNum][sceneNum] = !selectedScenes.value[episodeNum][sceneNum]
}

function toggleScriptVisibility(episodeNum, sceneNum) {
  const key = `${episodeNum}-${sceneNum}`
  expandedScenes.value[key] = !expandedScenes.value[key]
}

function toggleEpisode(episodeNum) {
  const allSelected = isEpisodeSelected(episodeNum)
  const episode = selectedScenes.value[episodeNum]

  Object.keys(episode).forEach(sceneNum => {
    episode[sceneNum] = !allSelected
  })
}

function isEpisodeSelected(episodeNum) {
  const episode = selectedScenes.value[episodeNum]
  if (!episode) return false
  return Object.values(episode).every(v => v === true)
}

function isEpisodeIndeterminate(episodeNum) {
  const episode = selectedScenes.value[episodeNum]
  if (!episode) return false
  const values = Object.values(episode)
  const selected = values.filter(v => v).length
  return selected > 0 && selected < values.length
}

function getEpisodeSelectedCount(episodeNum) {
  const episode = selectedScenes.value[episodeNum]
  if (!episode) return 0
  return Object.values(episode).filter(v => v).length
}

function selectAll() {
  storyStore.scenes.forEach(episode => {
    episode.scenes.forEach(scene => {
      selectedScenes.value[episode.episode][scene.scene_number] = true
    })
  })
}

function clearSelection() {
  storyStore.scenes.forEach(episode => {
    episode.scenes.forEach(scene => {
      selectedScenes.value[episode.episode][scene.scene_number] = false
    })
  })
}

function confirmManualInput() {
  showManualInput.value = false
  manualOverride.value = true
}

// 文件上传相关
function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileSelect(event) {
  const file = event.target.files?.[0]
  if (file) processFile(file)
}

function handleDrop(event) {
  isDragOver.value = false
  const file = event.dataTransfer.files?.[0]
  if (file) processFile(file)
}

function processFile(file) {
  const reader = new FileReader()
  reader.onload = (e) => {
    let text = e.target.result
    if (file.name.endsWith('.json')) {
      try {
        const obj = JSON.parse(text)
        text = obj.script || obj.content || obj.text || JSON.stringify(obj, null, 2)
      } catch (err) {
        console.error('Failed to parse JSON:', err)
      }
    }
    uploadedScript.value = text.trim()
    error.value = ''
    shots.value = []
  }
  reader.readAsText(file)
}

// 获取要解析的剧本
function getScript() {
  if (manualOverride.value) {
    if (pastedScript.value) return pastedScript.value.trim()
    if (uploadedScript.value) return uploadedScript.value.trim()
    return ''
  }
  if (hasStoryData.value) {
    return generateScriptFromSelection()
  } else if (pastedScript.value) {
    return pastedScript.value.trim()
  } else if (uploadedScript.value) {
    return uploadedScript.value.trim()
  }
  return ''
}

// 从选中的场景生成剧本文本
function generateScriptFromSelection() {
  const parts = []

  storyStore.scenes.forEach(episode => {
    const selectedInEpisode = episode.scenes.filter(scene =>
      selectedScenes.value[episode.episode]?.[scene.scene_number]
    )

    if (selectedInEpisode.length > 0) {
      parts.push(`第 ${episode.episode} 集：${episode.title}\n`)

      selectedInEpisode.forEach(scene => {
        parts.push(`\n【场景 ${scene.scene_number}】`)
        parts.push(`环境：${scene.environment}`)
        parts.push(`画面：${scene.visual}`)

        if (scene.audio && scene.audio.length > 0) {
          scene.audio.forEach(a => {
            parts.push(`${a.character}：${a.line}`)
          })
        }
        parts.push('')
      })
    }
  })

  return parts.join('\n')
}

function isAuthError(msg) {
  return /401|403|invalid|incorrect|unauthorized|api.?key/i.test(msg)
}

// 解析分镜
async function parseStoryboard() {
  if (!settings.useMock && !settings.effectiveLlmApiKey) {
    showKeyModal.value = true
    return
  }

  const script = getScript()

  if (!script) {
    error.value = '请先选择场景或输入剧本内容'
    return
  }

  isParsing.value = true
  error.value = ''
  shots.value = []
  progress.value = { show: true, label: '正在调用 LLM 解析分镜...', percent: 20 }

  // Mock 模式
  if (settings.useMock) {
    progress.value = { show: true, label: 'Mock 模式：生成模拟分镜...', percent: 50 }

    await new Promise(resolve => setTimeout(resolve, 800))

    const mockShots = [
      {
        shot_id: 'scene1_shot1',
        visual_description_zh: '清晨的森林，阳光透过树叶洒下斑驳光影，一只小鹿在溪边饮水',
        visual_prompt: 'A serene forest in early morning, sunlight filtering through lush green leaves creating dappled shadows on the forest floor, a young deer drinking from a crystal clear stream, mist rising, soft golden lighting, peaceful atmosphere, high detail, cinematic style',
        camera_motion: 'Slow pan right',
        dialogue: '在这片古老的森林里，每一天都是新的开始。',
        estimated_duration: 4,
        ttsLoading: false,
        imageLoading: false,
        videoLoading: false
      },
      {
        shot_id: 'scene1_shot2',
        visual_description_zh: '小鹿抬起头，警觉地望向远方，耳朵微微竖起',
        visual_prompt: 'Close-up of a young deer lifting its head, alert expression, ears perked up, water droplets falling from its mouth, soft bokeh background of forest greenery, warm morning light, detailed fur texture, wildlife photography style',
        camera_motion: 'Zoom in slowly',
        dialogue: null,
        estimated_duration: 3,
        ttsLoading: false,
        imageLoading: false,
        videoLoading: false
      },
      {
        shot_id: 'scene1_shot3',
        visual_description_zh: '远处传来脚步声，树枝被踩断的特写',
        visual_prompt: 'Extreme close-up of a dry twig snapping underfoot, forest floor covered with fallen autumn leaves, shallow depth of field, dramatic side lighting, tension building, cinematic thriller style',
        camera_motion: 'Static',
        dialogue: '沙沙的脚步声打破了森林的宁静...',
        estimated_duration: 4,
        ttsLoading: false,
        imageLoading: false,
        videoLoading: false
      },
      {
        shot_id: 'scene1_shot4',
        visual_description_zh: '一个身穿绿色斗篷的身影从树后走出，手持地图',
        visual_prompt: 'A mysterious figure in a flowing green cloak emerging from behind an ancient oak tree, holding an old parchment map, face partially hidden in shadow, forest background with sun rays, fantasy adventure style, detailed fabric texture',
        camera_motion: 'Medium shot, track forward',
        dialogue: '终于找到了...传说中的精灵之泉。',
        estimated_duration: 5,
        ttsLoading: false,
        imageLoading: false,
        videoLoading: false
      }
    ]

    progress.value = { show: true, label: '解析完成', percent: 100 }
    shots.value = mockShots

    setTimeout(() => {
      progress.value.show = false
    }, 500)

    isParsing.value = false
    return
  }

  try {
    const projectId = generateUniqueId()

    progress.value = { show: true, label: 'LLM 处理中，请稍候...', percent: 60 }

    const res = await fetch(`${getBackendUrl()}/api/v1/pipeline/${projectId}/storyboard`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getHeaders()
      },
      body: JSON.stringify({
        script,
        provider: settings.provider,
        model: settings.model
      })
    })

    if (!res.ok) {
      const errData = await res.json()
      throw new Error(errData.detail || '请求失败')
    }

    progress.value = { show: true, label: '解析完成，渲染卡片...', percent: 90 }
    const data = await res.json()
    shots.value = data.shots.map(s => ({ ...s, ttsLoading: false, imageLoading: false, videoLoading: false }))

    // 更新 token 统计
    if (data.usage) {
      storyStore.usage.prompt_tokens += data.usage.prompt_tokens || 0
      storyStore.usage.completion_tokens += data.usage.completion_tokens || 0
    }

    progress.value = { show: true, label: '完成', percent: 100 }

    setTimeout(() => {
      progress.value.show = false
    }, 800)
  } catch (err) {
    const msg = err.message || '请求失败'
    if (isAuthError(msg)) {
      keyModalType.value = 'invalid'
      keyModalMsg.value = 'API Key 无效或已过期，请检查后重新设置。'
      showKeyModal.value = true
    } else {
      error.value = '错误：' + msg
    }
    progress.value.show = false
  } finally {
    isParsing.value = false
  }
}

function getBackendUrl() {
  // 开发环境使用代理，避免 CORS 问题
  if (import.meta.env.DEV) {
    return ''
  }
  return settings.backendUrl || 'http://localhost:8000'
}

function getMediaUrl(path) {
  if (!path) return ''
  if (path.startsWith('http')) return path
  return `${getBackendUrl()}${path}`
}

function getHeaders() {
  const headers = {}
  if (settings.effectiveLlmApiKey)   headers['X-LLM-API-Key']   = settings.effectiveLlmApiKey
  if (settings.effectiveLlmBaseUrl)  headers['X-LLM-Base-URL']  = settings.effectiveLlmBaseUrl
  if (settings.effectiveLlmProvider) headers['X-LLM-Provider']  = settings.effectiveLlmProvider
  if (settings.effectiveImageApiKey)  headers['X-Image-API-Key']  = settings.effectiveImageApiKey
  if (settings.effectiveImageBaseUrl) headers['X-Image-Base-URL'] = settings.effectiveImageBaseUrl
  if (settings.effectiveVideoApiKey)  headers['X-Video-API-Key']  = settings.effectiveVideoApiKey
  if (settings.effectiveVideoBaseUrl) headers['X-Video-Base-URL'] = settings.effectiveVideoBaseUrl
  return headers
}

// TTS/Image/Video 生成函数
async function loadVoices() {
  try {
    const res = await fetch(`${getBackendUrl()}/api/v1/tts/voices`, { headers: getHeaders() })
    if (!res.ok) {
      console.error('Failed to load voices:', res.status, res.statusText)
      voices.value = []
      return
    }
    voices.value = await res.json()
    if (voices.value.length > 0) {
      selectedVoice.value = voices.value[0].id
    }
  } catch (err) {
    console.error('Failed to load voices:', err)
    voices.value = []
  }
}

async function generateOneTTS(shotId) {
  // Edge TTS 不需要 API Key，无需守卫

  const shot = shots.value.find(s => s.shot_id === shotId)
  if (!shot || !shot.dialogue) return

  shot.ttsLoading = true
  try {
    const res = await fetch(`${getBackendUrl()}/api/v1/tts/${generateUniqueId()}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify({ shots: [shot], voice: selectedVoice.value })
    })
    if (!res.ok) {
      const errData = await res.json().catch(() => null)
      throw new Error(errData?.detail || `TTS 请求失败 (${res.status})`)
    }
    const results = await res.json()
    const r = results[0]
    shot.audio_url = r.audio_url
    shot.audio_duration = r.duration_seconds
  } catch (err) {
    console.error('TTS failed:', err)
    const msg = err.message || '请求失败'
    if (isAuthError(msg)) {
      keyModalType.value = 'invalid'
      keyModalMsg.value = 'API Key 无效或已过期，请检查后重新设置。'
      showKeyModal.value = true
    } else {
      error.value = '语音生成失败：' + msg
    }
  } finally {
    shot.ttsLoading = false
  }
}

async function generateAllTTS() {
  const shotsWithDialogue = shots.value.filter(s => s.dialogue)
  await runWithConcurrency(shotsWithDialogue, s => generateOneTTS(s.shot_id))
}

async function generateOneImage(shotId) {
  if (!settings.useMock && !settings.effectiveImageApiKey) {
    showKeyModal.value = true
    return
  }

  const shot = shots.value.find(s => s.shot_id === shotId)
  if (!shot) return

  shot.imageLoading = true
  try {
    const res = await fetch(`${getBackendUrl()}/api/v1/image/${generateUniqueId()}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify({
        shots: [shot],
        ...(settings.effectiveImageModel ? { model: settings.effectiveImageModel } : {}),
      })
    })
    if (!res.ok) {
      const errData = await res.json().catch(() => null)
      throw new Error(errData?.detail || `图片生成失败 (${res.status})`)
    }
    const results = await res.json()
    const r = results[0]
    shot.image_url = r.image_url
  } catch (err) {
    console.error('Image generation failed:', err)
    const msg = err.message || '请求失败'
    if (isAuthError(msg)) {
      keyModalType.value = 'invalid'
      keyModalMsg.value = 'API Key 无效或已过期，请检查后重新设置。'
      showKeyModal.value = true
    } else {
      error.value = '图片生成失败：' + msg
    }
  } finally {
    shot.imageLoading = false
  }
}

async function generateAllImages() {
  await runWithConcurrency(shots.value, s => generateOneImage(s.shot_id))
}

async function generateOneVideo(shotId) {
  if (!settings.useMock && !settings.effectiveVideoApiKey) {
    showKeyModal.value = true
    return
  }

  const shot = shots.value.find(s => s.shot_id === shotId)
  if (!shot || !shot.image_url) return

  shot.videoLoading = true
  try {
    const res = await fetch(`${getBackendUrl()}/api/v1/video/${generateUniqueId()}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify({
        shots: [shot],
        ...(settings.effectiveVideoModel ? { model: settings.effectiveVideoModel } : {}),
      })
    })
    if (!res.ok) {
      const errData = await res.json().catch(() => null)
      throw new Error(errData?.detail || `视频生成失败 (${res.status})`)
    }
    const results = await res.json()
    const r = results[0]
    shot.video_url = r.video_url
  } catch (err) {
    console.error('Video generation failed:', err)
    const msg = err.message || '请求失败'
    if (isAuthError(msg)) {
      keyModalType.value = 'invalid'
      keyModalMsg.value = 'API Key 无效或已过期，请检查后重新设置。'
      showKeyModal.value = true
    } else {
      error.value = '视频生成失败：' + msg
    }
  } finally {
    shot.videoLoading = false
  }
}

async function generateAllVideos() {
  const shotsWithImages = shots.value.filter(s => s.image_url)
  await runWithConcurrency(shotsWithImages, s => generateOneVideo(s.shot_id))
}

onMounted(() => {
  loadVoices()

  // 初始化场景选择
  if (hasStoryData.value) {
    initSelectedScenes()
    // 默认选中第一个场景
    const firstEpisode = storyStore.scenes[0]
    if (firstEpisode && firstEpisode.scenes.length > 0) {
      selectedScenes.value[firstEpisode.episode][firstEpisode.scenes[0].scene_number] = true
    }
  }
})
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: #f5f5f7;
  color: #333;
  padding: 40px 24px;
}

.content {
  max-width: 900px;
  margin: 0 auto;
}

h1 {
  font-size: 22px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #1a1a1a;
}

.subtitle {
  color: #666;
  margin-bottom: 32px;
  font-size: 14px;
}

/* 导入区域 */
.story-import {
  max-width: 900px;
  margin: 0 auto;
}

.import-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: linear-gradient(135deg, #f0eeff 0%, #fff 100%);
  border: 1px solid #e0e0e0;
  border-bottom: none;
  border-radius: 12px 12px 0 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.import-icon {
  font-size: 20px;
}

.import-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
}

.scene-count {
  font-size: 13px;
  color: #6c63ff;
  font-weight: 600;
  background: #fff;
  padding: 4px 12px;
  border-radius: 12px;
  border: 1px solid #d0d0ff;
}

.import-actions {
  display: flex;
  gap: 8px;
  padding: 12px 20px;
  background: #fafafa;
  border: 1px solid #e0e0e0;
  border-bottom: none;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #fff;
  color: #666;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  border-color: #6c63ff;
  color: #6c63ff;
  background: #f0eeff;
}

/* 场景列表（参照 SceneStream） */
.episode-list {
  border: 1px solid #e0e0e0;
  border-radius: 0 0 12px 12px;
  overflow: hidden;
}

.episode-card {
  border-bottom: 1px solid #e0e0e0;
}

.episode-card:last-child {
  border-bottom: none;
}

.ep-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #f8f8f8;
  cursor: pointer;
  transition: background 0.2s;
  user-select: none;
}

.ep-header:hover {
  background: #f0f0f0;
}

.ep-checkbox {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.ep-badge {
  background: #6c63ff;
  color: #fff;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}

.ep-title {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.ep-count {
  font-size: 12px;
  color: #999;
  background: #fff;
  padding: 2px 8px;
  border-radius: 10px;
}

.scenes {
  padding: 0;
}

.scene-block {
  border-top: 1px solid #f0f0f0;
  transition: background 0.2s;
}

.scene-block.selected {
  background: #f0eeff;
}

.scene-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #fff;
  cursor: pointer;
  transition: background 0.2s;
}

.scene-header:hover {
  background: #fafafa;
}

.scene-checkbox {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.scene-num {
  color: #6c63ff;
  font-weight: 600;
  font-size: 13px;
  flex: 1;
}

.toggle-script-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: #f0f0f0;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #666;
  font-size: 12px;
  transition: all 0.2s;
  padding: 0;
}

.toggle-script-btn:hover {
  background: #e0e0ff;
  color: #6c63ff;
}

.toggle-script-btn.expanded {
  transform: rotate(180deg);
  background: #f0eeff;
  color: #6c63ff;
}

.scene-content {
  padding: 0 16px 12px 42px;
  overflow: hidden;
  transition: max-height 0.3s ease, padding 0.3s ease, opacity 0.3s ease;
  max-height: 500px;
  opacity: 1;
}

.scene-content.collapsed {
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
  opacity: 0;
}

.scene-row {
  margin-bottom: 6px;
  font-size: 13px;
  line-height: 1.6;
}

.scene-tag {
  color: #999;
  font-weight: 600;
}

.scene-text {
  color: #333;
}

.audio-lines {
  margin-top: 8px;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 6px;
  border-left: 3px solid #6c63ff;
}

.audio-line {
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 4px;
}

.character {
  color: #6c63ff;
  font-weight: 600;
}

.line {
  color: #555;
}

/* 空状态 */
.empty-state {
  max-width: 600px;
  margin: 60px auto;
  padding: 48px 32px;
  text-align: center;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin-bottom: 8px;
}

.empty-desc {
  font-size: 14px;
  color: #999;
  margin-bottom: 24px;
}

.empty-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.primary-btn,
.secondary-btn {
  padding: 10px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.primary-btn {
  background: #6c63ff;
  color: #fff;
  border: none;
}

.primary-btn:hover {
  background: #5a52e0;
}

.secondary-btn {
  background: #fff;
  color: #666;
  border: 1px solid #e0e0e0;
}

.secondary-btn:hover {
  border-color: #6c63ff;
  color: #6c63ff;
}

/* 模态框 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: #fff;
  border-radius: 12px;
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e0e0e0;
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: #f5f5f5;
  border-radius: 50%;
  cursor: pointer;
  font-size: 18px;
  color: #666;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #e0e0e0;
  color: #333;
}

.modal-body {
  padding: 20px;
  flex: 1;
  overflow-y: auto;
}

.tabs {
  display: flex;
  gap: 0;
  margin-bottom: 16px;
}

.tab-btn {
  background: none;
  border: 1px solid #e0e0e0;
  border-bottom: none;
  border-radius: 8px 8px 0 0;
  color: #888;
  padding: 8px 20px;
  font-size: 13px;
  cursor: pointer;
  transition: color 0.2s, background 0.2s;
}

.tab-btn.active {
  background: #fff;
  color: #6c63ff;
  border-color: #d0d0d0;
}

.tab-btn:hover:not(.active) {
  color: #555;
}

.upload-area {
  border: 2px dashed #d0d0d0;
  border-radius: 8px;
  padding: 40px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.upload-area:hover,
.upload-area.drag-over {
  border-color: #6c63ff;
  background: #f0eeff;
}

.upload-area p {
  color: #888;
  font-size: 14px;
  margin-top: 8px;
}

.script-textarea {
  width: 100%;
  min-height: 120px;
  background: #fafafa;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  color: #333;
  font-size: 13px;
  padding: 12px;
  resize: vertical;
  line-height: 1.6;
  font-family: inherit;
}

.script-textarea:focus {
  border-color: #6c63ff;
  outline: none;
}

.script-textarea::placeholder {
  color: #aaa;
}

.modal-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding: 16px 20px;
  border-top: 1px solid #e0e0e0;
}

.cancel-btn,
.confirm-btn {
  padding: 10px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.cancel-btn {
  background: #fff;
  color: #666;
  border: 1px solid #e0e0e0;
}

.cancel-btn:hover {
  border-color: #999;
}

.confirm-btn {
  background: #6c63ff;
  color: #fff;
  border: none;
}

.confirm-btn:hover {
  background: #5a52e0;
}

/* Controls */
.controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 20px;
  max-width: 600px;
}

.parse-btn {
  background: linear-gradient(135deg, #6c63ff 0%, #8b7fff 100%);
  color: #fff;
  border: none;
  border-radius: 12px;
  padding: 14px 48px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
  box-shadow: 0 4px 12px rgba(108, 99, 255, 0.3);
}

.parse-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #5a52e0 0%, #7566e8 100%);
  box-shadow: 0 6px 16px rgba(108, 99, 255, 0.4);
  transform: translateY(-1px);
}

.parse-btn:disabled {
  background: #ccc;
  cursor: not-allowed;
  box-shadow: none;
  transform: none;
}

select {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  color: #333;
  padding: 8px 12px;
  font-size: 13px;
  cursor: pointer;
}

button {
  background: #6c63ff;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 10px 24px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}

button:hover:not(:disabled) {
  background: #5a52e0;
}

button:disabled {
  background: #ccc;
  cursor: not-allowed;
}

/* Progress */
.progress-section {
  max-width: 600px;
  margin-top: 20px;
}

.progress-label {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.progress-bar {
  height: 4px;
  background: #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #6c63ff;
  width: 0%;
  transition: width 0.4s;
  border-radius: 4px;
}

/* Error */
.error-message {
  color: #e53935;
  font-size: 13px;
  margin-top: 16px;
  max-width: 600px;
  background: #fff;
  border-left: 4px solid #e53935;
  border-radius: 8px;
  padding: 12px;
}

/* Storyboard */
.storyboard {
  margin-top: 40px;
}

.storyboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.storyboard-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: #1a1a1a;
}

.action-group {
  display: flex;
  gap: 8px;
  align-items: center;
}

.voice-select {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  color: #333;
  padding: 6px 10px;
  font-size: 13px;
}

.action-btn {
  font-size: 13px;
  padding: 8px 20px;
}

.shots-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.shot-card {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  padding: 16px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.shot-card:hover {
  border-color: #6c63ff;
  box-shadow: 0 2px 12px rgba(108, 99, 255, 0.1);
}

.shot-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.shot-id {
  font-size: 11px;
  font-weight: 700;
  color: #6c63ff;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.shot-meta {
  display: flex;
  gap: 6px;
}

.tag {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 20px;
  background: #f0f0f0;
  color: #888;
}

.tag.type {
  background: #f0eeff;
  color: #6c63ff;
}

.shot-field {
  margin-bottom: 10px;
}

.shot-field label {
  font-size: 10px;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  display: block;
  margin-bottom: 4px;
}

.shot-field p {
  font-size: 13px;
  color: #333;
  line-height: 1.5;
}

.shot-field .en {
  font-size: 12px;
  color: #888;
  font-style: italic;
}

.tts-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}

.tts-btn {
  font-size: 11px;
  padding: 4px 12px;
  border-radius: 6px;
  background: #f0eeff;
  color: #6c63ff;
  border: 1px solid #d0d0ff;
  cursor: pointer;
}

.tts-btn:hover:not(:disabled) {
  background: #e0d9ff;
}

.tts-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.tts-duration {
  font-size: 11px;
  color: #999;
}

.shot-image {
  width: 100%;
  border-radius: 6px;
  margin-top: 8px;
}

.shot-video {
  width: 100%;
  border-radius: 6px;
  margin-top: 8px;
}
</style>
