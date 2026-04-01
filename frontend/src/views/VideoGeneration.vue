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
            <span class="scene-count">已选择 {{ selectedCount }}/{{ totalScenes }} 个场景 · 环境图组 {{ readyEpisodeReferenceCount }}/{{ storyStore.scenes.length }}</span>
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

            <div class="episode-key-art-panel">
              <div class="episode-key-art-top">
                <div>
                  <div class="episode-key-art-title">本集共享环境图组</div>
                  <div class="episode-key-art-subtitle">同集相似场景共用一组图，每组只生成一张主场景参考图，差异大的场景会额外拆组</div>
                </div>
                <span class="episode-key-art-status" :class="getEpisodeReferenceStatus(ep.episode)">
                  {{ formatSceneReferenceStatus(getEpisodeReferenceStatus(ep.episode)) }}
                </span>
              </div>
              <div v-if="getEpisodeReferenceGroups(ep.episode).length" class="episode-key-art-group-list">
                <div
                  v-if="getEpisodeReferenceGroups(ep.episode).length > 1"
                  class="episode-key-art-group-tabs"
                >
                  <button
                    v-for="(group, index) in getEpisodeReferenceGroups(ep.episode)"
                    :key="getEpisodeReferenceGroupKey(group, index)"
                    type="button"
                    class="episode-key-art-group-tab"
                    :class="{ active: getActiveEpisodeReferenceGroupKey(ep.episode) === getEpisodeReferenceGroupKey(group, index) }"
                    @click.stop="setActiveEpisodeReferenceGroup(ep.episode, group, index)"
                  >
                    {{ group.group_label || `环境组 ${index + 1}` }}
                  </button>
                </div>
                <div
                  v-if="getActiveEpisodeReferenceGroup(ep.episode)"
                  class="episode-key-art-group"
                >
                  <div class="episode-key-art-group-top">
                    <div class="episode-key-art-group-title">{{ getActiveEpisodeReferenceGroup(ep.episode).group_label || '环境组' }}</div>
                    <div class="episode-key-art-group-copy">
                      覆盖场景：{{ formatSceneNumbers(getActiveEpisodeReferenceGroup(ep.episode).affected_scene_numbers) }} · {{ getActiveEpisodeReferenceGroup(ep.episode).summary_environment || '主环境' }}
                    </div>
                  </div>
                  <div class="episode-key-art-grid">
                    <div
                      class="episode-key-art-card"
                    >
                      <img
                        v-if="getActiveEpisodeReferenceGroup(ep.episode).variants?.scene?.image_url"
                        :src="getMediaUrl(getActiveEpisodeReferenceGroup(ep.episode).variants.scene.image_url)"
                        class="episode-key-art-image"
                      />
                      <div v-else class="episode-key-art-placeholder">Scene Reference</div>
                      <div class="episode-key-art-label">主场景参考图</div>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="episode-key-art-empty">
                还没有生成环境组。点击下方按钮后，会按本集场景环境自动拆成 1 组或多组。
              </div>
              <div class="episode-key-art-actions">
                <button
                  class="episode-key-art-btn"
                  :disabled="getEpisodeReferenceStatus(ep.episode) === 'loading'"
                  @click.stop="generateEpisodeReference(ep)"
                >
                  {{ getEpisodeReferenceGroups(ep.episode).length ? '重新生成本集环境图组' : '生成本集环境图组' }}
                </button>
                <span v-if="getEpisodeReferenceError(ep.episode)" class="episode-key-art-error">
                  {{ getEpisodeReferenceError(ep.episode) }}
                </span>
              </div>
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
                  <div class="scene-reference-usage">
                    <span class="scene-reference-usage-label">环境图组</span>
                    <span class="scene-reference-usage-value">
                      {{ getSceneReferenceGroupLabel(ep.episode, scene.scene_number) }} · {{ formatSceneReferenceStatus(getSceneReferenceAsset(ep.episode, scene.scene_number).status) }}
                    </span>
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
            <select v-if="speechGenerationEnabled" v-model="selectedVoice" class="voice-select">
              <option v-for="voice in voices" :key="voice.id" :value="voice.id">
                {{ voice.name }}
              </option>
            </select>
            <button v-if="speechGenerationEnabled" class="action-btn" @click="generateAllTTS">全部生成语音</button>
            <button class="action-btn" @click="generateAllImages">全部生成图片</button>
            <button class="action-btn" @click="generateAllVideos">全部生成视频</button>
            <button
              v-if="shots.length > 0"
              class="action-btn concat-btn"
              :disabled="concatLoading || !exportReadiness.ready"
              @click="concatAllVideos"
            >
              {{ concatLoading ? '拼接中...' : '导出完整视频' }}
            </button>
          </div>
        </div>
        <div v-if="shots.length > 0 && !exportReadiness.ready" class="export-readiness-note">
          {{ exportReadiness.message }}
        </div>
        <div class="transition-note">
          过渡视频现已接入后端。双帧只用于 transition，本页会从相邻两个主镜头视频中抽取对应帧，不影响普通主镜头生成链路。
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

              <div v-if="speechGenerationEnabled && hasSpeechAudio(item.shot)" class="tts-bar">
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
                    <span class="transition-status-badge" :class="{ ready: item.ready || !!item.result?.video_url }">
                      {{ item.loading ? 'Generating' : (item.result?.video_url ? 'Generated' : (item.ready ? 'Ready' : 'Pending')) }}
                    </span>
                  </div>
                </div>
                <span class="transition-pair">{{ item.fromShot.shot_id }} -> {{ item.toShot.shot_id }}</span>
              </div>
              <div class="transition-preview-strip">
                <div class="transition-frame">
                  <div class="transition-frame-label">前镜参考帧</div>
                  <img
                    v-if="item.result?.first_frame_source?.extracted_image_url || item.fromShot.image_url"
                    :src="getMediaUrl(item.result?.first_frame_source?.extracted_image_url || item.fromShot.image_url)"
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
                    v-if="item.result?.last_frame_source?.extracted_image_url || item.toShot.image_url"
                    :src="getMediaUrl(item.result?.last_frame_source?.extracted_image_url || item.toShot.image_url)"
                    class="transition-frame-image"
                  />
                  <div v-else class="transition-frame-placeholder">等待目标首帧</div>
                </div>
              </div>
              <video
                v-if="item.result?.video_url"
                :src="getMediaUrl(item.result.video_url)"
                controls
                class="shot-video"
              ></video>
              <p class="transition-copy">
                {{ item.result?.video_url
                  ? '过渡视频已生成。当前会严格使用前镜最后一帧和后镜第一帧，避免主题漂移。'
                  : item.ready
                    ? '前后镜头视频已就绪，可以生成过渡片段。后端会只读取这两个相邻视频的对应帧。'
                    : '等待前后镜头视频都准备好后，再进入可生成状态。'
                }}
              </p>
              <div class="transition-meta">
                <span class="transition-chip">建议时长 1-2s</span>
                <span class="transition-pill" :class="{ active: !!item.fromShot.video_url }">前镜视频</span>
                <span class="transition-pill" :class="{ active: !!item.toShot.video_url }">后镜视频</span>
              </div>
              <div class="transition-action-row">
                <button
                  class="transition-btn"
                  :class="{ disabled: !item.ready || item.loading }"
                  :disabled="!item.ready || item.loading"
                  @click="previewTransitionSlot(item)"
                >
                  {{ item.loading ? '生成中...' : (item.result?.video_url ? '重新生成过渡视频' : (item.ready ? '生成过渡视频' : '过渡视频待就绪')) }}
                </button>
                <span class="transition-hint">
                  {{ item.result?.video_url ? '已接入后端，可重新生成覆盖当前结果' : (item.ready ? '将从两侧视频中抽取对应帧' : '先补齐两侧视频') }}
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
import { generateEpisodeSceneReference, generatePipelineTransition, getHeaders, getPipelineStatus } from '../api/story.js'
import StepIndicator from '../components/StepIndicator.vue'
import ApiKeyModal from '../components/ApiKeyModal.vue'
import { resolveBackendBaseUrl, resolveBackendMediaUrl } from '../utils/backend.js'
import { canAccessStep, getStepRedirectPath } from '../utils/stepAccess.js'

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
const speechGenerationEnabled = false
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
const concatVideoUrl = ref(storyStore.storyboardFinalVideoUrl || storyStore.meta?.storyboard_generation?.final_video_url || '')
const manualProjectId = ref(storyStore.manualProjectId || storyStore.storyId || '')
const manualPipelineId = ref(storyStore.manualPipelineId || '')
const manualStoryId = ref(storyStore.manualStoryId || storyStore.storyId || '')
const transitionLoadingMap = ref({})
const episodeReferenceErrors = ref({})
const activeEpisodeReferenceGroupKeys = ref({})

const transitionResults = computed(() => {
  const generatedFiles = storyStore.meta?.storyboard_generation?.generated_files
  return generatedFiles?.transitions && typeof generatedFiles.transitions === 'object'
    ? generatedFiles.transitions
    : {}
})
const transitionTimeline = computed(() => {
  const generatedFiles = storyStore.meta?.storyboard_generation?.generated_files
  return Array.isArray(generatedFiles?.timeline) ? generatedFiles.timeline : []
})

function buildTransitionId(fromShotId, toShotId) {
  return `transition_${fromShotId}__${toShotId}`
}

function buildLocalTimeline(shotsList = [], transitionsMap = {}) {
  const timeline = []
  const safeTransitions = transitionsMap && typeof transitionsMap === 'object' ? transitionsMap : {}

  for (let i = 0; i < shotsList.length; i += 1) {
    const shotId = shotsList[i]?.shot_id
    if (!shotId) continue

    timeline.push({ item_type: 'shot', item_id: shotId })

    if (i + 1 >= shotsList.length) continue

    const nextShotId = shotsList[i + 1]?.shot_id
    if (!nextShotId) continue

    const transitionId = buildTransitionId(shotId, nextShotId)
    if (safeTransitions[transitionId]?.video_url) {
      timeline.push({ item_type: 'transition', item_id: transitionId })
    }
  }

  return timeline
}

function effectivePipelineId() {
  return manualPipelineId.value || storyStore.meta?.storyboard_generation?.pipeline_id || ''
}

function invalidateLocalTransitionArtifacts(shotId, { clearShotVideo = false } = {}) {
  if (!shotId) return

  const currentGeneratedFiles = storyStore.meta?.storyboard_generation?.generated_files
  const nextGeneratedFiles = currentGeneratedFiles && typeof currentGeneratedFiles === 'object'
    ? { ...currentGeneratedFiles }
    : {}

  const nextTransitions = nextGeneratedFiles.transitions && typeof nextGeneratedFiles.transitions === 'object'
    ? { ...nextGeneratedFiles.transitions }
    : {}

  Object.keys(nextTransitions).forEach(transitionId => {
    if (transitionId.includes(`_${shotId}__`) || transitionId.endsWith(`__${shotId}`)) {
      delete nextTransitions[transitionId]
    }
  })

  nextGeneratedFiles.transitions = nextTransitions

  if (clearShotVideo) {
    const nextVideos = nextGeneratedFiles.videos && typeof nextGeneratedFiles.videos === 'object'
      ? { ...nextGeneratedFiles.videos }
      : {}
    delete nextVideos[shotId]
    nextGeneratedFiles.videos = nextVideos
  }

  nextGeneratedFiles.final_video_url = ''
  nextGeneratedFiles.timeline = buildLocalTimeline(shots.value, nextTransitions)

  storyStore.syncStoryboardGenerationMeta({
    generatedFiles: nextGeneratedFiles,
    replaceGeneratedFiles: true,
  })
  storyStore.syncStoryboardGenerationMeta({ shots: shots.value })
  concatVideoUrl.value = ''
  storyStore.setStoryboardFinalVideoUrl('')
}

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
    const transitionId = buildTransitionId(shot.shot_id, nextShot.shot_id)
    const result = transitionResults.value[transitionId] || null

    items.push({
      type: 'transition',
      key: `transition-${shot.shot_id}-${nextShot.shot_id}`,
      transitionId,
      fromShot: shot,
      toShot: nextShot,
      result,
      loading: !!transitionLoadingMap.value[transitionId],
      ready: !!shot.video_url && !!nextShot.video_url,
    })
  }
  return items
})

const exportReadiness = computed(() => {
  if (shots.value.length === 0) {
    return {
      ready: false,
      missingShotVideos: [],
      missingTransitions: [],
      message: '当前还没有可导出的分镜。',
    }
  }

  const missingShotVideos = shots.value
    .filter(shot => !shot?.video_url)
    .map(shot => shot.shot_id)

  const missingTransitions = []
  for (let i = 0; i < shots.value.length - 1; i += 1) {
    const transitionId = buildTransitionId(shots.value[i].shot_id, shots.value[i + 1].shot_id)
    if (!transitionResults.value[transitionId]?.video_url) {
      missingTransitions.push(transitionId)
    }
  }

  const ready = missingShotVideos.length === 0 && missingTransitions.length === 0
  if (ready) {
    return {
      ready: true,
      missingShotVideos,
      missingTransitions,
      message: '',
    }
  }

  const parts = []
  if (missingShotVideos.length > 0) {
    parts.push(`缺少主镜头视频：${missingShotVideos.join('、')}`)
  }
  if (missingTransitions.length > 0) {
    parts.push(`缺少过渡视频：${missingTransitions.join('、')}`)
  }

  return {
    ready: false,
    missingShotVideos,
    missingTransitions,
    message: `导出完整视频前，当前核心分镜和相邻过渡分镜必须全部生成完成。${parts.join('；')}`,
  }
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

  if (replaceStoryboard) {
    const hasTts = Object.prototype.hasOwnProperty.call(generatedFiles, 'tts')
    const hasImages = Object.prototype.hasOwnProperty.call(generatedFiles, 'images')
    const hasVideos = Object.prototype.hasOwnProperty.call(generatedFiles, 'videos')
    const ttsMap = hasTts && generatedFiles.tts && typeof generatedFiles.tts === 'object' ? generatedFiles.tts : {}
    const imageMap = hasImages && generatedFiles.images && typeof generatedFiles.images === 'object' ? generatedFiles.images : {}
    const videoMap = hasVideos && generatedFiles.videos && typeof generatedFiles.videos === 'object' ? generatedFiles.videos : {}

    shots.value.forEach(shot => {
      if (hasTts && !ttsMap[shot.shot_id]) {
        delete shot.audio_url
        delete shot.audio_duration
      }
      if (hasImages && !imageMap[shot.shot_id]) {
        delete shot.image_url
      }
      if (hasVideos && !videoMap[shot.shot_id]) {
        delete shot.video_url
      }
    })
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
    })
  })

  Object.values(generatedFiles.videos || {}).forEach(result => {
    updateShot(result.shot_id, shot => {
      shot.video_url = result.video_url
    })
  })

  if (replaceStoryboard && !generatedFiles.final_video_url) {
    concatVideoUrl.value = ''
    storyStore.setStoryboardFinalVideoUrl('')
  }

  if (generatedFiles.final_video_url) {
    concatVideoUrl.value = generatedFiles.final_video_url
    storyStore.setStoryboardFinalVideoUrl(generatedFiles.final_video_url)
  }

  storyStore.syncStoryboardGenerationMeta({
    generatedFiles,
    replaceGeneratedFiles: replaceStoryboard,
  })
  storyStore.syncStoryboardGenerationMeta({
    shots: shots.value,
    finalVideoUrl: concatVideoUrl.value,
    projectId: manualProjectId.value || storyStore.storyId || '',
    pipelineId: effectivePipelineId(),
    storyId: manualStoryId.value || storyStore.storyId || '',
  })
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
    updateShotsFromGeneratedFiles(state.generated_files, { replaceStoryboard: true })

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
  const pipelineId = effectivePipelineId()
  if (!projectId) {
    if (storyId) {
      console.warn('Skip restoring pipeline state because projectId is missing', { storyId })
    }
    return null
  }

  try {
    const state = await getPipelineStatus(projectId, {
      pipelineId,
      storyId,
    })
    rememberManualPipelineContext({
      projectId: projectId || state.project_id || state.story_id || '',
      pipelineId: state.pipeline_id || pipelineId,
      storyId: state.story_id || storyId,
    })
    updateShotsFromGeneratedFiles(state.generated_files, { replaceStoryboard: true })
    return state
  } catch (err) {
    console.warn('Failed to restore latest pipeline state:', err)
    return null
  }
}

// 计算属性
const hasStoryData = computed(() => {
  return storyStore.scenes && storyStore.scenes.length > 0
})
const readyEpisodeReferenceCount = computed(() =>
  storyStore.scenes.filter(episode => storyStore.getEpisodeSceneReferenceStatus(episode.episode) === 'ready').length
)

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
function getSceneReferenceAsset(episode, sceneNumber) {
  return storyStore.sceneReferenceAssets?.[storyStore.getSceneKey(episode, sceneNumber)] || {
    status: 'idle',
    variants: {},
    error: '',
  }
}

function getEpisodeReferenceSceneNumber(episode) {
  const episodeData = storyStore.scenes.find(item => item.episode === episode)
  return episodeData?.scenes?.[0]?.scene_number || 1
}

function getEpisodeReferenceGroups(episode) {
  return storyStore.getEpisodeSceneReferenceGroups(episode)
}

function getEpisodeReferenceGroupKey(group, index = 0) {
  if (group?.environment_pack_key) return group.environment_pack_key
  if (group?.group_label) return `${group.group_label}-${index}`
  return `group-${index + 1}`
}

function getActiveEpisodeReferenceGroupKey(episode) {
  const groups = getEpisodeReferenceGroups(episode)
  if (!groups.length) return ''

  const selectedKey = activeEpisodeReferenceGroupKeys.value[episode]
  const hasSelectedGroup = groups.some((group, index) => getEpisodeReferenceGroupKey(group, index) === selectedKey)
  if (hasSelectedGroup) return selectedKey

  return getEpisodeReferenceGroupKey(groups[0], 0)
}

function getActiveEpisodeReferenceGroup(episode) {
  const groups = getEpisodeReferenceGroups(episode)
  const activeKey = getActiveEpisodeReferenceGroupKey(episode)
  return groups.find((group, index) => getEpisodeReferenceGroupKey(group, index) === activeKey) || null
}

function setActiveEpisodeReferenceGroup(episode, group, index = 0) {
  activeEpisodeReferenceGroupKeys.value = {
    ...activeEpisodeReferenceGroupKeys.value,
    [episode]: getEpisodeReferenceGroupKey(group, index),
  }
}

function getEpisodeReferenceStatus(episode) {
  return storyStore.getEpisodeSceneReferenceStatus(episode)
}

function getEpisodeReferenceError(episode) {
  return episodeReferenceErrors.value[episode] || getEpisodeReferenceGroups(episode).find(group => group.error)?.error || ''
}

function getSceneReferenceGroupLabel(episode, sceneNumber) {
  const asset = getSceneReferenceAsset(episode, sceneNumber)
  if (!asset.environment_pack_key) return '待匹配环境组'
  const sceneNumbers = Array.isArray(asset.affected_scene_numbers)
    ? asset.affected_scene_numbers.map(number => String(number).padStart(2, '0')).join(' / ')
    : '--'
  return `${asset.group_label || asset.environment_pack_key} · 场景 ${sceneNumbers}`
}

function formatSceneNumbers(numbers = []) {
  return numbers.length ? numbers.map(number => String(number).padStart(2, '0')).join(' / ') : '--'
}

function formatSceneReferenceStatus(status) {
  return {
    idle: '未生成',
    loading: '生成中',
    ready: '已就绪',
    failed: '失败',
    stale: '需刷新',
  }[status] || '未生成'
}

async function generateEpisodeReference(episode) {
  const seedScene = episode?.scenes?.[0]
  if (!seedScene) return
  storyStore.setEpisodeSceneReferenceStatus(episode.episode, 'loading', '')
  episodeReferenceErrors.value = {
    ...episodeReferenceErrors.value,
    [episode.episode]: '',
  }
  try {
    const forceRegenerate = storyStore.getEpisodeSceneReferenceGroups(episode.episode).length > 0
    const result = await generateEpisodeSceneReference(storyStore.storyId, episode.episode, { forceRegenerate })
    storyStore.applyEpisodeSceneReferenceAsset(result)
    const nextGroups = storyStore.getEpisodeSceneReferenceGroups(episode.episode)
    if (nextGroups.length > 0) {
      setActiveEpisodeReferenceGroup(episode.episode, nextGroups[0], 0)
    }
    episodeReferenceErrors.value = {
      ...episodeReferenceErrors.value,
      [episode.episode]: '',
    }
  } catch (error) {
    const message = error.message || '环境图生成失败'
    episodeReferenceErrors.value = {
      ...episodeReferenceErrors.value,
      [episode.episode]: message,
    }
    storyStore.setEpisodeSceneReferenceStatus(episode.episode, 'failed', message)
  }
}

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

function createApiError(status, detail, fallbackMessage = '请求失败') {
  const error = new Error(detail || fallbackMessage)
  error.status = status
  return error
}

async function readApiError(response, fallbackMessage = '请求失败') {
  let detail = ''
  try {
    const errData = await response.json()
    detail = errData?.detail || ''
  } catch {
    detail = ''
  }
  return createApiError(response.status, detail || `${fallbackMessage} (${response.status})`)
}

// 解析分镜
async function parseStoryboard() {
  const script = getScript()

  if (!script) {
    error.value = '请先选择场景或输入剧本内容'
    return
  }

  isParsing.value = true
  error.value = ''
  transitionMessage.value = ''
  episodeReferenceErrors.value = {}
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
      throw await readApiError(res, '请求失败')
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
    if (err.status === 400) {
      keyModalType.value = 'missing'
      keyModalMsg.value = '缺少 API Key，请先在设置页填写可用的密钥。'
      showKeyModal.value = true
    } else if (isAuthError(msg)) {
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
  return resolveBackendBaseUrl(settings.backendUrl)
}

function getMediaUrl(path) {
  return resolveBackendMediaUrl(path, settings.backendUrl)
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
  return generateTransitionForSlot(item)
}

async function generateTransitionForSlot(item) {
  if (!item?.fromShot || !item?.toShot) return
  if (!item.ready) {
    const missing = []
    if (!item.fromShot.video_url) missing.push(item.fromShot.shot_id)
    if (!item.toShot.video_url) missing.push(item.toShot.shot_id)
    transitionMessage.value = `过渡槽位尚未就绪：请先为 ${missing.join(' 和 ')} 生成视频。`
    return
  }

  const pipelineId = effectivePipelineId()
  if (!pipelineId) {
    error.value = '当前还没有可用的 pipeline_id，请先完成分镜解析。'
    return
  }

  const transitionId = item.transitionId || buildTransitionId(item.fromShot.shot_id, item.toShot.shot_id)
  transitionLoadingMap.value = {
    ...transitionLoadingMap.value,
    [transitionId]: true,
  }
  error.value = ''
  transitionMessage.value = ''

  try {
    const projectId = resolveManualProjectId()
    const result = await generatePipelineTransition(projectId, {
      pipeline_id: pipelineId,
      story_id: effectiveStoryId(),
      from_shot_id: item.fromShot.shot_id,
      to_shot_id: item.toShot.shot_id,
      transition_prompt: item.toShot.transition_from_previous || '',
      duration_seconds: 2,
      ...(settings.effectiveVideoModel ? { model: settings.effectiveVideoModel } : {}),
    })

    const state = await getPipelineStatus(projectId, {
      pipelineId,
      storyId: effectiveStoryId(),
    })
    rememberManualPipelineContext({
      projectId,
      pipelineId: state.pipeline_id || pipelineId,
      storyId: state.story_id || effectiveStoryId(),
    })
    updateShotsFromGeneratedFiles(state.generated_files, { replaceStoryboard: true })
    transitionMessage.value = `过渡视频已生成：${result.from_shot_id} -> ${result.to_shot_id}`
  } catch (err) {
    console.error('Transition generation failed:', err)
    error.value = '过渡视频生成失败：' + (err.message || '请求失败')
  } finally {
    transitionLoadingMap.value = {
      ...transitionLoadingMap.value,
      [transitionId]: false,
    }
  }
}

async function generateOneTTS(shotId) {
  // Edge TTS 不需要 API Key，无需守卫

  const shot = shots.value.find(s => s.shot_id === shotId)
  if (!hasSpeechAudio(shot)) return

  shot.ttsLoading = true
  try {
    const projectId = resolveManualProjectId()
    const res = await fetch(`${getBackendUrl()}/api/v1/tts/${projectId}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify({
        shots: [shot],
        voice: selectedVoice.value,
        story_id: effectiveStoryId(),
        pipeline_id: effectivePipelineId() || undefined,
      })
    })
    if (!res.ok) {
      const errData = await res.json().catch(() => null)
      throw new Error(errData?.detail || `TTS 请求失败 (${res.status})`)
    }
    const results = await res.json()
    const r = results[0]
    shot.audio_url = r.audio_url
    shot.audio_duration = r.duration_seconds
    storyStore.syncStoryboardGenerationMeta({ shots: shots.value })
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
    const pipelineId = effectivePipelineId()
    const query = buildPipelineQuery({
      pipeline_id: pipelineId,
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
        pipeline_id: pipelineId || undefined,
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
      pipelineId: data.pipeline_id || pipelineId,
      storyId: data.story_id || fallbackStoryId,
    })
    updateShotsFromGeneratedFiles(data.state?.generated_files, { replaceStoryboard: true })

    await pollManualPipeline({
      projectId,
      pipelineId: data.pipeline_id || pipelineId,
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
    const projectId = resolveManualProjectId()
    const res = await fetch(`${getBackendUrl()}/api/v1/image/${projectId}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify({
        shots: [shot],
        story_id: effectiveStoryId(),
        pipeline_id: effectivePipelineId() || undefined,
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
    if (effectivePipelineId()) {
      try {
        const state = await getPipelineStatus(projectId, {
          pipelineId: effectivePipelineId(),
          storyId: effectiveStoryId(),
        })
        rememberManualPipelineContext({
          projectId,
          pipelineId: state.pipeline_id || effectivePipelineId(),
          storyId: state.story_id || effectiveStoryId(),
        })
        updateShotsFromGeneratedFiles(state.generated_files, { replaceStoryboard: true })
      } catch (syncErr) {
        console.warn('Failed to refresh pipeline state after image generation:', syncErr)
        delete shot.video_url
        invalidateLocalTransitionArtifacts(shotId, { clearShotVideo: true })
      }
    } else {
      delete shot.video_url
      invalidateLocalTransitionArtifacts(shotId, { clearShotVideo: true })
    }
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
    const pipelineId = effectivePipelineId()
    const query = buildPipelineQuery({
      pipeline_id: pipelineId,
      story_id: fallbackStoryId,
      generate_tts: false,
      generate_images: true,
      image_model: settings.effectiveImageModel || undefined,
    })

    const res = await fetch(`${getBackendUrl()}/api/v1/pipeline/${projectId}/generate-assets${query}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify({
        pipeline_id: pipelineId || undefined,
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
      pipelineId: data.pipeline_id || pipelineId,
      storyId: data.story_id || fallbackStoryId,
    })
    updateShotsFromGeneratedFiles(data.state?.generated_files, { replaceStoryboard: true })

    await pollManualPipeline({
      projectId,
      pipelineId: data.pipeline_id || pipelineId,
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
    const projectId = resolveManualProjectId()
    const res = await fetch(`${getBackendUrl()}/api/v1/video/${projectId}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify({
        shots: [shot],
        story_id: effectiveStoryId(),
        pipeline_id: effectivePipelineId() || undefined,
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
    if (effectivePipelineId()) {
      try {
        const state = await getPipelineStatus(projectId, {
          pipelineId: effectivePipelineId(),
          storyId: effectiveStoryId(),
        })
        rememberManualPipelineContext({
          projectId,
          pipelineId: state.pipeline_id || effectivePipelineId(),
          storyId: state.story_id || effectiveStoryId(),
        })
        updateShotsFromGeneratedFiles(state.generated_files, { replaceStoryboard: true })
      } catch (syncErr) {
        console.warn('Failed to refresh pipeline state after video generation:', syncErr)
        invalidateLocalTransitionArtifacts(shotId)
      }
    } else {
      invalidateLocalTransitionArtifacts(shotId)
    }
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
    const pipelineId = effectivePipelineId()
    const query = buildPipelineQuery({
      pipeline_id: pipelineId,
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
      pipelineId: data.pipeline_id || pipelineId,
      storyId: data.story_id || fallbackStoryId,
    })
    updateShotsFromGeneratedFiles(data.state?.generated_files, { replaceStoryboard: true })

    await pollManualPipeline({
      projectId,
      pipelineId: data.pipeline_id || pipelineId,
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
  const projectId = resolveManualProjectId()
  const fallbackStoryId = manualStoryId.value || storyStore.storyId || projectId
  const pipelineId = effectivePipelineId()

  error.value = ''
  transitionMessage.value = ''

  if (pipelineId) {
    try {
      const latestState = await getPipelineStatus(projectId, {
        pipelineId,
        storyId: fallbackStoryId,
      })
      rememberManualPipelineContext({
        projectId,
        pipelineId: latestState.pipeline_id || pipelineId,
        storyId: latestState.story_id || fallbackStoryId,
      })
      updateShotsFromGeneratedFiles(latestState.generated_files, { replaceStoryboard: true })
    } catch (syncErr) {
      console.warn('Failed to refresh pipeline state before concat:', syncErr)
    }
  }

  if (!exportReadiness.value.ready) {
    error.value = exportReadiness.value.message
    return
  }

  const shotMap = Object.fromEntries(shots.value.filter(s => s?.shot_id).map(s => [s.shot_id, s]))
  const orderedVideoUrls = []

  if (transitionTimeline.value.length > 0) {
    transitionTimeline.value.forEach(item => {
      if (item?.item_type === 'shot') {
        const videoUrl = shotMap[item.item_id]?.video_url
        if (videoUrl) orderedVideoUrls.push(videoUrl)
        return
      }
      if (item?.item_type === 'transition') {
        const videoUrl = transitionResults.value[item.item_id]?.video_url
        if (videoUrl) orderedVideoUrls.push(videoUrl)
      }
    })
  } else {
    storyboardFlowItems.value.forEach(item => {
      if (item.type === 'shot' && item.shot?.video_url) {
        orderedVideoUrls.push(item.shot.video_url)
        return
      }
      if (item.type === 'transition' && item.result?.video_url) {
        orderedVideoUrls.push(item.result.video_url)
      }
    })
  }

  if (orderedVideoUrls.length === 0) return

  concatLoading.value = true
  concatVideoUrl.value = ''

  try {
    const query = buildPipelineQuery({
      pipeline_id: pipelineId,
      story_id: fallbackStoryId,
    })

    const res = await fetch(`${getBackendUrl()}/api/v1/pipeline/${projectId}/concat${query}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify({
        video_urls: orderedVideoUrls
      })
    })
    if (!res.ok) {
      const errData = await res.json().catch(() => null)
      throw new Error(errData?.detail || `拼接失败 (${res.status})`)
    }
    const data = await res.json()
    rememberManualPipelineContext({
      projectId,
      pipelineId: data.pipeline_id || pipelineId,
      storyId: data.story_id || fallbackStoryId,
    })
    concatVideoUrl.value = data.video_url
    storyStore.setStoryboardFinalVideoUrl(data.video_url)
  } catch (err) {
    console.error('Concat failed:', err)
    error.value = '视频拼接失败：' + (err.message || '请求失败')
  } finally {
    concatLoading.value = false
  }
}

onMounted(async () => {
  if (!canAccessStep(storyStore, 5)) {
    router.replace(getStepRedirectPath(storyStore, 5))
    return
  }

  if (speechGenerationEnabled) {
    loadVoices()
  }
  storyStore.ensureSceneReferenceAssets()
  concatVideoUrl.value = storyStore.storyboardFinalVideoUrl || storyStore.meta?.storyboard_generation?.final_video_url || ''
  rememberManualPipelineContext({
    projectId: manualProjectId.value || storyStore.storyId || '',
    storyId: manualStoryId.value || storyStore.storyId || '',
  })

  await restoreLatestPipelineState()

  // 恢复持久化的 shots 时重置 loading 状态（防止刷新前正在生成导致状态卡住）
  storyStore.shots.forEach(s => {
    s.ttsLoading = false
    s.imageLoading = false
    s.videoLoading = false
  })
  storyStore.syncStoryboardGenerationMeta({
    shots: storyStore.shots,
    finalVideoUrl: concatVideoUrl.value,
    projectId: manualProjectId.value || storyStore.storyId || '',
    pipelineId: effectivePipelineId(),
    storyId: manualStoryId.value || storyStore.storyId || '',
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

<style scoped src="../style/videogeneration.css"></style>
