<template>
  <div class="page">
    <StepIndicator :current="5" :loading="isParsing || isGenerating || concatLoading" />
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
      <div v-if="transitionMessage" class="info-message">
        {{ transitionMessage }}
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
            <button
              v-if="hasAnyVideo"
              class="action-btn concat-btn"
              :disabled="concatLoading"
              @click="concatAllVideos"
            >
              {{ concatLoading ? '拼接中...' : '导出完整视频' }}
            </button>
          </div>
        </div>
        <div class="transition-note">
          过渡视频能力当前仅展示前端 UI。这里先预留相邻镜头之间的插槽和状态文案，暂不调用后端接口，也不会改变现有生成与导出逻辑。
        </div>
        <div class="shots-grid">
          <template v-for="item in storyboardFlowItems" :key="item.key">
            <div v-if="item.type === 'shot'" class="shot-card">
              <div class="shot-header">
                <span class="shot-id">{{ item.shot.shot_id }}</span>
                <div class="shot-meta">
                  <span class="tag type">{{ item.shot.camera_setup?.movement || item.shot.camera_motion }}</span>
                  <span class="tag">{{ item.shot.estimated_duration }}s</span>
                </div>
              </div>
              <div v-if="hasSpeechAudio(item.shot)" class="shot-field">
                <label>台词 / 旁白</label>
                <p>{{ item.shot.audio_reference?.content || item.shot.dialogue }}</p>
              </div>
              <div class="shot-field">
                <label>画面描述</label>
                <p>{{ item.shot.storyboard_description || item.shot.visual_description_zh }}</p>
              </div>
              <div v-if="item.shot.image_prompt" class="shot-field">
                <label>Image Prompt</label>
                <p class="en">{{ item.shot.image_prompt }}</p>
              </div>
              <div class="shot-field">
                <label>Video Prompt</label>
                <p class="en">{{ item.shot.final_video_prompt || item.shot.visual_prompt }}</p>
              </div>

              <div v-if="hasSpeechAudio(item.shot)" class="tts-bar">
                <button class="tts-btn" @click="generateOneTTS(item.shot.shot_id)" :disabled="item.shot.ttsLoading">
                  {{ item.shot.ttsLoading ? '生成中...' : '生成语音' }}
                </button>
                <audio v-if="item.shot.audio_url" :src="getMediaUrl(item.shot.audio_url)" controls style="height: 28px; flex: 1"></audio>
                <span v-if="item.shot.audio_duration" class="tts-duration">{{ item.shot.audio_duration.toFixed(1) }}s</span>
              </div>

              <div class="tts-bar">
                <button class="tts-btn" @click="generateOneImage(item.shot.shot_id)" :disabled="item.shot.imageLoading">
                  {{ item.shot.imageLoading ? '生成中...' : '生成图片' }}
                </button>
              </div>
              <img v-if="item.shot.image_url" :src="getMediaUrl(item.shot.image_url)" class="shot-image" />
              <div v-if="item.shot.image_url" class="tts-bar">
                <button class="tts-btn" @click="generateOneImage(item.shot.shot_id)" :disabled="item.shot.imageLoading">重新生成图片</button>
                <button class="tts-btn" @click="generateOneVideo(item.shot.shot_id)" :disabled="item.shot.videoLoading">
                  {{ item.shot.videoLoading ? '生成中...' : '生成视频' }}
                </button>
              </div>
              <video v-if="item.shot.video_url" :src="getMediaUrl(item.shot.video_url)" controls class="shot-video"></video>
            </div>

            <div v-else class="transition-slot" :class="{ ready: item.ready }">
              <div class="transition-slot-top">
                <div class="transition-heading">
                  <span class="transition-kicker">Transition Slot</span>
                  <div class="transition-title-row">
                    <div class="transition-title">过渡视频</div>
                    <span class="transition-status-badge" :class="{ ready: item.ready }">
                      {{ item.ready ? 'Ready' : 'Pending' }}
                    </span>
                  </div>
                </div>
                <span class="transition-pair">{{ item.fromShot.shot_id }} -> {{ item.toShot.shot_id }}</span>
              </div>
              <div class="transition-preview-strip">
                <div class="transition-frame">
                  <div class="transition-frame-label">前镜尾部</div>
                  <img
                    v-if="item.fromShot.last_frame_url || item.fromShot.image_url"
                    :src="getMediaUrl(item.fromShot.last_frame_url || item.fromShot.image_url)"
                    class="transition-frame-image"
                  />
                  <div v-else class="transition-frame-placeholder">等待首帧素材</div>
                </div>
                <div class="transition-arrow-wrap">
                  <span class="transition-arrow-line"></span>
                  <span class="transition-arrow-text">过渡</span>
                </div>
                <div class="transition-frame">
                  <div class="transition-frame-label">后镜首部</div>
                  <img
                    v-if="item.toShot.image_url"
                    :src="getMediaUrl(item.toShot.image_url)"
                    class="transition-frame-image"
                  />
                  <div v-else class="transition-frame-placeholder">等待目标首帧</div>
                </div>
              </div>
              <p class="transition-copy">
                {{ item.ready
                  ? '前后镜头素材已就绪，可在这里插入过渡片段。当前仅展示 UI，不会真正发起生成。'
                  : '等待前后镜头至少生成出图片或视频后，再进入可生成状态。当前仅保留界面占位。'
                }}
              </p>
              <div class="transition-meta">
                <span class="transition-chip">建议时长 1-2s</span>
                <span class="transition-pill" :class="{ active: !!item.fromShot.video_url }">前镜视频</span>
                <span class="transition-pill" :class="{ active: !!(item.toShot.video_url || item.toShot.image_url) }">后镜首帧</span>
              </div>
              <div class="transition-action-row">
                <button class="transition-btn" :class="{ disabled: !item.ready }" @click="previewTransitionSlot(item)">
                  {{ item.ready ? '生成过渡视频（UI预留）' : '过渡视频待就绪' }}
                </button>
                <span class="transition-hint">
                  {{ item.ready ? '下一步可接后端生成接口' : '先补齐两侧素材' }}
                </span>
              </div>
            </div>
          </template>
        </div>

        <!-- 完整视频播放器 -->
        <div v-if="concatVideoUrl" class="concat-result">
          <h3>完整视频</h3>
          <video :src="getMediaUrl(concatVideoUrl)" controls class="concat-video"></video>
          <a :href="getMediaUrl(concatVideoUrl)" download class="action-btn download-btn">下载完整视频</a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSettingsStore } from '../stores/settings.js'
import { useStoryStore } from '../stores/story.js'
import { getHeaders, getPipelineStatus } from '../api/story.js'
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
const isGenerating = ref(false)
const error = ref('')
const transitionMessage = ref('')
const shots = computed(() => storyStore.shots)
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

const isMounted = ref(true)
let parseAbortController = null
onUnmounted(() => {
  isMounted.value = false
  parseAbortController?.abort()
})

// 视频拼接
const concatLoading = ref(false)
const concatVideoUrl = ref('')
const manualProjectId = ref(storyStore.manualProjectId || storyStore.storyId || '')
const manualPipelineId = ref(storyStore.manualPipelineId || '')
const manualStoryId = ref(storyStore.manualStoryId || storyStore.storyId || '')

const hasAnyVideo = computed(() => shots.value.some(s => s.video_url))
const storyboardFlowItems = computed(() => {
  const items = []
  for (let i = 0; i < shots.value.length; i += 1) {
    const shot = shots.value[i]
    items.push({
      type: 'shot',
      key: `shot-${shot.shot_id}`,
      shot,
    })

    const nextShot = shots.value[i + 1]
    if (!nextShot) continue

    items.push({
      type: 'transition',
      key: `transition-${shot.shot_id}-${nextShot.shot_id}`,
      fromShot: shot,
      toShot: nextShot,
      ready: !!shot.video_url && !!(nextShot.video_url || nextShot.image_url),
    })
  }
  return items
})

// 生成唯一 ID
function generateUniqueId() {
  return `ui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function resolveManualProjectId() {
  if (storyStore.storyId) {
    rememberManualPipelineContext({
      projectId: storyStore.storyId,
      storyId: storyStore.storyId,
    })
    return storyStore.storyId
  }
  if (!manualProjectId.value) {
    manualProjectId.value = generateUniqueId()
    storyStore.setManualPipelineContext({ projectId: manualProjectId.value })
  }
  return manualProjectId.value
}

function effectiveStoryId() {
  return manualStoryId.value || storyStore.storyId || manualProjectId.value
}

function rememberManualPipelineContext({ projectId, pipelineId, storyId } = {}) {
  if (projectId) manualProjectId.value = projectId
  if (pipelineId) manualPipelineId.value = pipelineId
  if (storyId) manualStoryId.value = storyId
  storyStore.setManualPipelineContext({
    projectId: manualProjectId.value,
    pipelineId: manualPipelineId.value,
    storyId: manualStoryId.value,
  })
}

function buildPipelineQuery(params = {}) {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    searchParams.set(key, String(value))
  })
  const query = searchParams.toString()
  return query ? `?${query}` : ''
}

function updateShotsFromGeneratedFiles(generatedFiles = {}, { replaceStoryboard = false } = {}) {
  if (!generatedFiles || typeof generatedFiles !== 'object') return

  const storyboardShots = generatedFiles.storyboard?.shots
  if (Array.isArray(storyboardShots) && (replaceStoryboard || shots.value.length === 0)) {
    storyStore.setShots(storyboardShots)
  }

  const updateShot = (shotId, updater) => {
    const shot = shots.value.find(s => s.shot_id === shotId)
    if (!shot) return
    updater(shot)
  }

  Object.values(generatedFiles.tts || {}).forEach(result => {
    updateShot(result.shot_id, shot => {
      shot.audio_url = result.audio_url
      shot.audio_duration = result.duration_seconds
    })
  })

  Object.values(generatedFiles.images || {}).forEach(result => {
    updateShot(result.shot_id, shot => {
      shot.image_url = result.image_url
      shot.last_frame_url = result.last_frame_url || null
    })
  })

  Object.values(generatedFiles.videos || {}).forEach(result => {
    updateShot(result.shot_id, shot => {
      shot.video_url = result.video_url
    })
  })

  if (generatedFiles.final_video_url) {
    concatVideoUrl.value = generatedFiles.final_video_url
  }
}

async function pollManualPipeline({ projectId, pipelineId, storyId, isDone, timeoutMs = 180000, intervalMs = 1200 }) {
  const startedAt = Date.now()

  while (Date.now() - startedAt < timeoutMs) {
    const res = await fetch(
      `${getBackendUrl()}/api/v1/pipeline/${projectId}/status${buildPipelineQuery({
        pipeline_id: pipelineId,
        story_id: storyId,
      })}`,
      { headers: getHeaders() }
    )

    if (!res.ok) {
      const errData = await res.json().catch(() => null)
      throw new Error(errData?.detail || `状态查询失败 (${res.status})`)
    }

    const state = await res.json()
    rememberManualPipelineContext({
      projectId,
      pipelineId: state.pipeline_id || pipelineId,
      storyId: state.story_id || storyId,
    })
    updateShotsFromGeneratedFiles(state.generated_files)

    if (state.status === 'failed') {
      throw new Error(state.error || '批量任务失败')
    }
    if (isDone(state)) {
      return state
    }

    await new Promise(resolve => setTimeout(resolve, intervalMs))
  }

  throw new Error('批量任务等待超时')
}

async function restoreLatestPipelineState() {
  const projectId = manualProjectId.value || storyStore.storyId || ''
  const storyId = manualStoryId.value || storyStore.storyId || projectId
  if (!projectId) {
    if (storyId) {
      console.warn('Skip restoring pipeline state because projectId is missing', { storyId })
    }
    return
  }

  try {
    const state = await getPipelineStatus(projectId, {
      pipelineId: manualPipelineId.value,
      storyId,
    })
    rememberManualPipelineContext({
      projectId: projectId || state.project_id || state.story_id || '',
      pipelineId: state.pipeline_id || manualPipelineId.value,
      storyId: state.story_id || storyId,
    })
    updateShotsFromGeneratedFiles(state.generated_files, { replaceStoryboard: true })
  } catch (err) {
    console.warn('Failed to restore latest pipeline state:', err)
  }
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
    transitionMessage.value = ''
    storyStore.clearShots()
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
  transitionMessage.value = ''
  storyStore.clearShots()
  concatVideoUrl.value = ''
  progress.value = { show: true, label: '正在调用 LLM 解析分镜...', percent: 20 }

  parseAbortController?.abort()
  parseAbortController = new AbortController()
  const { signal } = parseAbortController

  // Mock 模式
  if (settings.useMock) {
    progress.value = { show: true, label: 'Mock 模式：生成模拟分镜...', percent: 50 }

    await new Promise(resolve => setTimeout(resolve, 800))

    const mockShots = [
      {
        shot_id: 'scene1_shot1',
        storyboard_description: '清晨的森林，阳光透过树叶洒下斑驳光影，一只小鹿在溪边饮水',
        final_video_prompt: 'Wide Shot, Eye-level, Slow pan right. A serene forest in early morning, sunlight filtering through lush green leaves creating dappled shadows on the forest floor, a young deer drinking from a crystal clear stream, mist rising. Warm golden hour lighting, soft shadows. Cinematic, 4k resolution, photorealistic, --ar 16:9',
        camera_setup: { shot_size: 'WS', camera_angle: 'Eye-level', movement: 'Pan right' },
        visual_elements: { subject_and_clothing: 'A young spotted deer', action_and_expression: 'Drinking from stream, calm posture', environment_and_props: 'Ancient forest, crystal stream, morning mist', lighting_and_color: 'Warm golden hour, soft dappled shadows through leaves' },
        audio_reference: { type: 'narration', content: '在这片古老的森林里，每一天都是新的开始。' },
        scene_intensity: 'low',
        estimated_duration: 4,
        mood: 'peaceful',
        scene_position: 'establishing',
        ttsLoading: false,
        imageLoading: false,
        videoLoading: false
      },
      {
        shot_id: 'scene1_shot2',
        storyboard_description: '小鹿抬起头，警觉地望向远方，耳朵微微竖起',
        final_video_prompt: 'Close-up, Eye-level, Zoom in slowly. A young spotted deer lifting its head alertly, ears perked up, water droplets falling from its mouth, soft bokeh forest greenery background. Warm morning light, detailed fur texture. Cinematic, 4k resolution, photorealistic, --ar 16:9',
        camera_setup: { shot_size: 'CU', camera_angle: 'Eye-level', movement: 'Slow Dolly in' },
        visual_elements: { subject_and_clothing: 'Young spotted deer, detailed fur', action_and_expression: 'Lifting head alertly, ears perked, water drops from mouth', environment_and_props: 'Soft bokeh forest greenery background', lighting_and_color: 'Warm morning light, soft fill' },
        audio_reference: { type: null, content: null },
        scene_intensity: 'low',
        estimated_duration: 3,
        mood: 'alert',
        scene_position: 'development',
        ttsLoading: false,
        imageLoading: false,
        videoLoading: false
      },
      {
        shot_id: 'scene1_shot3',
        storyboard_description: '远处传来脚步声，树枝被踩断的特写',
        final_video_prompt: 'Extreme Close-up, High angle, Static. A dry twig snapping underfoot on forest floor covered with fallen autumn leaves, shallow depth of field. Dramatic side lighting, tension building, desaturated color grading. Cinematic, 4k resolution, photorealistic, --ar 16:9',
        camera_setup: { shot_size: 'ECU', camera_angle: 'High angle', movement: 'Static' },
        visual_elements: { subject_and_clothing: 'Boot sole pressing on twig', action_and_expression: 'Twig snapping, leaves scattering slightly', environment_and_props: 'Forest floor, autumn leaves, shallow DoF', lighting_and_color: 'Dramatic side lighting, desaturated tones' },
        audio_reference: { type: 'narration', content: '沙沙的脚步声打破了森林的宁静...' },
        scene_intensity: 'high',
        estimated_duration: 4,
        mood: 'tense',
        scene_position: 'climax',
        ttsLoading: false,
        imageLoading: false,
        videoLoading: false
      },
      {
        shot_id: 'scene1_shot4',
        storyboard_description: '一个身穿绿色斗篷的身影从树后走出，手持地图',
        final_video_prompt: 'Medium Shot, Eye-level, Dolly forward. A mysterious figure in a flowing dark green wool cloak emerging from behind an ancient oak tree, holding an old parchment map, face partially hidden in deep shadow. Forest background with volumetric sun rays. Rim lighting on cloak edges, warm golden tones. Cinematic, 4k resolution, photorealistic, --ar 16:9',
        camera_setup: { shot_size: 'MS', camera_angle: 'Eye-level', movement: 'Slow Dolly in' },
        visual_elements: { subject_and_clothing: 'Mysterious figure, dark green wool cloak, old parchment map', action_and_expression: 'Emerging from behind tree, face hidden in shadow', environment_and_props: 'Ancient oak tree, forest with sun rays', lighting_and_color: 'Volumetric god rays, rim lighting on cloak, warm golden tones' },
        audio_reference: { type: 'dialogue', content: '终于找到了...传说中的精灵之泉。' },
        scene_intensity: 'low',
        estimated_duration: 5,
        mood: 'mysterious',
        scene_position: 'resolution',
        ttsLoading: false,
        imageLoading: false,
        videoLoading: false
      }
    ]

    progress.value = { show: true, label: '解析完成', percent: 100 }
    storyStore.setShots(mockShots)

    setTimeout(() => {
      if (isMounted.value) progress.value.show = false
    }, 500)

    isParsing.value = false
    return
  }

  try {
    const projectId = resolveManualProjectId()

    progress.value = { show: true, label: 'LLM 处理中，请稍候...', percent: 60 }

    const res = await fetch(`${getBackendUrl()}/api/v1/pipeline/${projectId}/storyboard`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getHeaders()
      },
      signal,
      body: JSON.stringify({
        script,
        provider: settings.provider,
        model: settings.model,
        story_id: effectiveStoryId(),
      })
    })

    if (!res.ok) {
      const errData = await res.json()
      throw new Error(errData.detail || '请求失败')
    }

    progress.value = { show: true, label: '解析完成，渲染卡片...', percent: 90 }
    const data = await res.json()
    rememberManualPipelineContext({
      projectId,
      pipelineId: data.pipeline_id || '',
      storyId: data.story_id || storyStore.storyId || projectId,
    })
    storyStore.setShots(data.shots)

    // 更新 token 统计
    if (data.usage) {
      storyStore.usage.prompt_tokens += data.usage.prompt_tokens || 0
      storyStore.usage.completion_tokens += data.usage.completion_tokens || 0
    }

    if (isMounted.value) {
      progress.value = { show: true, label: '完成', percent: 100 }
      setTimeout(() => {
        if (isMounted.value) progress.value.show = false
      }, 800)
    }
  } catch (err) {
    if (err.name === 'AbortError') return
    if (!isMounted.value) return
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
  const configured = settings.backendUrl?.replace(/\/$/, '')
  if (configured) return configured
  if (import.meta.env.DEV) return 'http://localhost:8000'
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin.replace(/\/$/, '')
  }
  return ''
}

function getMediaUrl(path) {
  if (!path) return ''
  if (path.startsWith('http')) return path
  return `${getBackendUrl()}${path}`
}

// TTS/Image/Video 生成函数
async function loadVoices() {
  try {
    const res = await fetch(`${getBackendUrl()}/api/v1/tts/voices`, { headers: getHeaders() })
    if (!res.ok) {
      console.error('Failed to load voices:', res.status, res.statusText)
      if (isMounted.value) voices.value = []
      return
    }
    const data = await res.json()
    if (!isMounted.value) return
    voices.value = data
    if (voices.value.length > 0) {
      selectedVoice.value = voices.value[0].id
    }
  } catch (err) {
    console.error('Failed to load voices:', err)
    if (isMounted.value) voices.value = []
  }
}

function hasSpeechAudio(shot) {
  return !!(shot && (shot.audio_reference?.content || shot.dialogue) && shot.audio_reference?.type !== 'sfx')
}

function previewTransitionSlot(item) {
  if (!item?.fromShot || !item?.toShot) return
  if (item.ready) {
    transitionMessage.value = `过渡视频 UI 已预留：${item.fromShot.shot_id} -> ${item.toShot.shot_id}。当前版本仅展示前端界面，后端生成接口暂未接入。`
    return
  }
  transitionMessage.value = `过渡槽位尚未就绪：请先为 ${item.fromShot.shot_id} 生成视频，并为 ${item.toShot.shot_id} 生成图片或视频。`
}

async function generateOneTTS(shotId) {
  // Edge TTS 不需要 API Key，无需守卫

  const shot = shots.value.find(s => s.shot_id === shotId)
  if (!hasSpeechAudio(shot)) return

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
    if (!isMounted.value) return
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
  const shotsWithDialogue = shots.value.filter(hasSpeechAudio)
  if (shotsWithDialogue.length === 0) return

  isGenerating.value = true
  error.value = ''
  transitionMessage.value = ''
  shotsWithDialogue.forEach(shot => { shot.ttsLoading = true })

  try {
    const projectId = resolveManualProjectId()
    const fallbackStoryId = manualStoryId.value || storyStore.storyId || projectId
    const query = buildPipelineQuery({
      pipeline_id: manualPipelineId.value,
      story_id: fallbackStoryId,
      voice: selectedVoice.value,
      generate_tts: true,
      generate_images: false,
      image_model: settings.effectiveImageModel || undefined,
    })

    const res = await fetch(`${getBackendUrl()}/api/v1/pipeline/${projectId}/generate-assets${query}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify({
        pipeline_id: manualPipelineId.value || undefined,
        story_id: fallbackStoryId,
        shots: shots.value,
      })
    })

    if (!res.ok) {
      const errData = await res.json().catch(() => null)
      throw new Error(errData?.detail || `批量语音生成失败 (${res.status})`)
    }

    const data = await res.json()
    rememberManualPipelineContext({
      projectId,
      pipelineId: data.pipeline_id || manualPipelineId.value,
      storyId: data.story_id || fallbackStoryId,
    })
    updateShotsFromGeneratedFiles(data.state?.generated_files)

    await pollManualPipeline({
      projectId,
      pipelineId: data.pipeline_id || manualPipelineId.value,
      storyId: data.story_id || fallbackStoryId,
      isDone: state => state.progress >= 60 && state.generated_files?.tts,
    })
  } catch (err) {
    if (!isMounted.value) return
    console.error('Batch TTS failed:', err)
    const msg = err.message || '请求失败'
    if (isAuthError(msg)) {
      keyModalType.value = 'invalid'
      keyModalMsg.value = 'API Key 无效或已过期，请检查后重新设置。'
      showKeyModal.value = true
    } else {
      error.value = '批量语音生成失败：' + msg
    }
  } finally {
    shotsWithDialogue.forEach(shot => { shot.ttsLoading = false })
    isGenerating.value = false
  }
}

async function generateOneImage(shotId) {
  const shot = shots.value.find(s => s.shot_id === shotId)
  if (!shot) return

  shot.imageLoading = true
  try {
    const res = await fetch(`${getBackendUrl()}/api/v1/image/${generateUniqueId()}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify({
        shots: [shot],
        story_id: effectiveStoryId(),
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
    shot.last_frame_url = r.last_frame_url || null
  } catch (err) {
    if (!isMounted.value) return
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
  if (shots.value.length === 0) return

  isGenerating.value = true
  error.value = ''
  transitionMessage.value = ''
  shots.value.forEach(shot => { shot.imageLoading = true })

  try {
    const projectId = resolveManualProjectId()
    const fallbackStoryId = manualStoryId.value || storyStore.storyId || projectId
    const query = buildPipelineQuery({
      pipeline_id: manualPipelineId.value,
      story_id: fallbackStoryId,
      generate_tts: false,
      generate_images: true,
      image_model: settings.effectiveImageModel || undefined,
    })

    const res = await fetch(`${getBackendUrl()}/api/v1/pipeline/${projectId}/generate-assets${query}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify({
        pipeline_id: manualPipelineId.value || undefined,
        story_id: fallbackStoryId,
        shots: shots.value,
      })
    })

    if (!res.ok) {
      const errData = await res.json().catch(() => null)
      throw new Error(errData?.detail || `批量图片生成失败 (${res.status})`)
    }

    const data = await res.json()
    rememberManualPipelineContext({
      projectId,
      pipelineId: data.pipeline_id || manualPipelineId.value,
      storyId: data.story_id || fallbackStoryId,
    })
    updateShotsFromGeneratedFiles(data.state?.generated_files)

    await pollManualPipeline({
      projectId,
      pipelineId: data.pipeline_id || manualPipelineId.value,
      storyId: data.story_id || fallbackStoryId,
      isDone: state => state.progress >= 60 && state.generated_files?.images,
    })
  } catch (err) {
    if (!isMounted.value) return
    console.error('Batch image generation failed:', err)
    const msg = err.message || '请求失败'
    if (isAuthError(msg)) {
      keyModalType.value = 'invalid'
      keyModalMsg.value = 'API Key 无效或已过期，请检查后重新设置。'
      showKeyModal.value = true
    } else {
      error.value = '批量图片生成失败：' + msg
    }
  } finally {
    shots.value.forEach(shot => { shot.imageLoading = false })
    isGenerating.value = false
  }
}

async function generateOneVideo(shotId) {
  const shot = shots.value.find(s => s.shot_id === shotId)
  if (!shot || !shot.image_url) return

  shot.videoLoading = true
  try {
    const res = await fetch(`${getBackendUrl()}/api/v1/video/${generateUniqueId()}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify({
        shots: [shot],
        story_id: effectiveStoryId(),
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
    if (!isMounted.value) return
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
  if (shotsWithImages.length === 0) return

  isGenerating.value = true
  error.value = ''
  transitionMessage.value = ''
  shotsWithImages.forEach(shot => { shot.videoLoading = true })

  try {
    const projectId = resolveManualProjectId()
    const fallbackStoryId = manualStoryId.value || storyStore.storyId || projectId
    const query = buildPipelineQuery({
      pipeline_id: manualPipelineId.value,
      story_id: fallbackStoryId,
      base_url: getBackendUrl(),
      video_model: settings.effectiveVideoModel || undefined,
    })

    const res = await fetch(`${getBackendUrl()}/api/v1/pipeline/${projectId}/render-video${query}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify(shotsWithImages)
    })

    if (!res.ok) {
      const errData = await res.json().catch(() => null)
      throw new Error(errData?.detail || `批量视频生成失败 (${res.status})`)
    }

    const data = await res.json()
    rememberManualPipelineContext({
      projectId,
      pipelineId: data.pipeline_id || manualPipelineId.value,
      storyId: data.story_id || fallbackStoryId,
    })
    updateShotsFromGeneratedFiles(data.state?.generated_files)

    await pollManualPipeline({
      projectId,
      pipelineId: data.pipeline_id || manualPipelineId.value,
      storyId: data.story_id || fallbackStoryId,
      isDone: state => state.progress >= 85 && state.generated_files?.videos,
    })
  } catch (err) {
    if (!isMounted.value) return
    console.error('Batch video generation failed:', err)
    const msg = err.message || '请求失败'
    if (isAuthError(msg)) {
      keyModalType.value = 'invalid'
      keyModalMsg.value = 'API Key 无效或已过期，请检查后重新设置。'
      showKeyModal.value = true
    } else {
      error.value = '批量视频生成失败：' + msg
    }
  } finally {
    shotsWithImages.forEach(shot => { shot.videoLoading = false })
    isGenerating.value = false
  }
}

async function concatAllVideos() {
  const shotsWithVideo = shots.value
    .filter(s => s.video_url)
    .sort((a, b) => a.shot_id.localeCompare(b.shot_id))

  if (shotsWithVideo.length === 0) return

  concatLoading.value = true
  concatVideoUrl.value = ''
  error.value = ''
  transitionMessage.value = ''

  try {
    const projectId = resolveManualProjectId()
    const fallbackStoryId = manualStoryId.value || storyStore.storyId || projectId
    const query = buildPipelineQuery({
      pipeline_id: manualPipelineId.value,
      story_id: fallbackStoryId,
    })

    const res = await fetch(`${getBackendUrl()}/api/v1/pipeline/${projectId}/concat${query}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify({
        video_urls: shotsWithVideo.map(s => s.video_url)
      })
    })
    if (!res.ok) {
      const errData = await res.json().catch(() => null)
      throw new Error(errData?.detail || `拼接失败 (${res.status})`)
    }
    const data = await res.json()
    rememberManualPipelineContext({
      projectId,
      pipelineId: data.pipeline_id || manualPipelineId.value,
      storyId: data.story_id || fallbackStoryId,
    })
    concatVideoUrl.value = data.video_url
  } catch (err) {
    console.error('Concat failed:', err)
    error.value = '视频拼接失败：' + (err.message || '请求失败')
  } finally {
    concatLoading.value = false
  }
}

onMounted(async () => {
  loadVoices()
  rememberManualPipelineContext({
    projectId: storyStore.storyId || manualProjectId.value || '',
    storyId: storyStore.storyId || manualStoryId.value || '',
  })

  await restoreLatestPipelineState()

  // 恢复持久化的 shots 时重置 loading 状态（防止刷新前正在生成导致状态卡住）
  storyStore.shots.forEach(s => {
    s.ttsLoading = false
    s.imageLoading = false
    s.videoLoading = false
  })

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

.info-message {
  color: #1d4ed8;
  font-size: 13px;
  margin-top: 16px;
  max-width: 600px;
  background: #eff6ff;
  border-left: 4px solid #60a5fa;
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

.transition-note {
  margin-bottom: 16px;
  padding: 14px 16px;
  border: 1px solid #d7d1bf;
  border-radius: 12px;
  background:
    linear-gradient(135deg, rgba(238, 231, 209, 0.95), rgba(246, 242, 232, 0.98));
  color: #63553a;
  font-size: 13px;
  line-height: 1.6;
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

.transition-slot {
  position: relative;
  overflow: hidden;
  background:
    linear-gradient(160deg, rgba(255, 248, 235, 0.98), rgba(247, 241, 228, 0.98));
  border: 1px dashed #d1b97c;
  border-radius: 12px;
  padding: 16px;
  min-height: 220px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.transition-slot::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  background: linear-gradient(180deg, #b7852d, #e1ca8a);
}

.transition-slot.ready {
  border-style: solid;
  border-color: #b7852d;
  box-shadow: 0 8px 24px rgba(183, 133, 45, 0.12);
}

.transition-slot-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.transition-heading {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.transition-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.transition-kicker {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #a07018;
}

.transition-pair {
  font-size: 11px;
  color: #8b7750;
  text-align: right;
  word-break: break-word;
}

.transition-title {
  font-size: 18px;
  font-weight: 700;
  color: #4f3d1d;
}

.transition-status-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  background: rgba(116, 103, 81, 0.12);
  color: #7f6d49;
  border: 1px solid rgba(116, 103, 81, 0.18);
}

.transition-status-badge.ready {
  background: rgba(183, 133, 45, 0.15);
  color: #87590f;
  border-color: rgba(183, 133, 45, 0.3);
}

.transition-preview-strip {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 72px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
}

.transition-frame {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.transition-frame-label {
  font-size: 10px;
  color: #8f7d59;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.transition-frame-image,
.transition-frame-placeholder {
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 10px;
}

.transition-frame-image {
  object-fit: cover;
  border: 1px solid rgba(177, 152, 97, 0.22);
  box-shadow: 0 8px 20px rgba(116, 93, 44, 0.08);
}

.transition-frame-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  text-align: center;
  font-size: 12px;
  color: #907f5d;
  background:
    linear-gradient(135deg, rgba(255, 252, 245, 0.9), rgba(239, 232, 214, 0.9));
  border: 1px dashed rgba(177, 152, 97, 0.35);
}

.transition-arrow-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.transition-arrow-line {
  position: relative;
  display: block;
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg, rgba(183, 133, 45, 0.15), rgba(183, 133, 45, 0.92));
}

.transition-arrow-line::after {
  content: '';
  position: absolute;
  top: 50%;
  right: -1px;
  width: 10px;
  height: 10px;
  border-top: 2px solid #b7852d;
  border-right: 2px solid #b7852d;
  transform: translateY(-50%) rotate(45deg);
}

.transition-arrow-text {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #b7852d;
}

.transition-copy {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #6c5b3b;
}

.transition-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: auto;
}

.transition-chip {
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(79, 61, 29, 0.08);
  color: #5e4a27;
  font-size: 11px;
  border: 1px solid rgba(79, 61, 29, 0.12);
}

.transition-pill {
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(122, 106, 69, 0.08);
  color: #8c7d5a;
  font-size: 11px;
  border: 1px solid rgba(122, 106, 69, 0.14);
}

.transition-pill.active {
  background: rgba(183, 133, 45, 0.15);
  color: #7a5311;
  border-color: rgba(183, 133, 45, 0.35);
}

.transition-btn {
  margin-top: 4px;
  border: none;
  border-radius: 10px;
  padding: 10px 14px;
  background: #b7852d;
  color: #fffaf1;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, opacity 0.2s, transform 0.2s;
}

.transition-btn:hover {
  background: #9f711f;
  transform: translateY(-1px);
}

.transition-btn.disabled {
  background: #cdb88c;
  cursor: not-allowed;
  transform: none;
}

.transition-action-row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.transition-hint {
  font-size: 11px;
  color: #8f7f5c;
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

@media (max-width: 720px) {
  .transition-slot-top {
    flex-direction: column;
  }

  .transition-pair {
    text-align: left;
  }

  .transition-preview-strip {
    grid-template-columns: 1fr;
  }

  .transition-arrow-wrap {
    min-height: 42px;
  }

  .transition-arrow-line {
    width: 2px;
    height: 28px;
    background: linear-gradient(180deg, rgba(183, 133, 45, 0.15), rgba(183, 133, 45, 0.92));
  }

  .transition-arrow-line::after {
    top: auto;
    right: 50%;
    bottom: -1px;
    transform: translateX(50%) rotate(135deg);
  }
}
/* 导出完整视频按钮 */
.concat-btn {
  background: #6c63ff;
  color: #fff;
  border-color: #6c63ff;
}

.concat-btn:hover:not(:disabled) {
  background: #5a52e0;
  border-color: #5a52e0;
}

.concat-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 完整视频播放区域 */
.concat-result {
  margin-top: 24px;
  padding: 20px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
}

.concat-result h3 {
  margin: 0 0 12px;
  font-size: 16px;
  font-weight: 600;
  color: #1a1a1a;
}

.concat-video {
  width: 100%;
  border-radius: 8px;
  margin-bottom: 12px;
}

.download-btn {
  display: inline-flex;
  text-decoration: none;
  background: #6c63ff;
  color: #fff;
  border-color: #6c63ff;
}

.download-btn:hover {
  background: #5a52e0;
  border-color: #5a52e0;
  color: #fff;
}

</style>
