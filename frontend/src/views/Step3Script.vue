<template>
  <div class="page">
    <StepIndicator :current="3" :loading="streaming" />
    <div class="content">
      <div class="title-row">
        <div>
          <h1>剧本生成</h1>
          <p class="subtitle">确认大纲后开始生成完整剧本</p>
        </div>
      </div>

      <div class="top-row">
        <div class="outline-col">
          <OutlinePreview
            v-if="store.meta"
            :meta="store.meta"
            :characters="store.characters"
            :outline="store.outline"
          />
        </div>
        <div class="graph-col">
          <CharacterGraph
            v-if="store.characters.length"
            :characters="store.characters"
            :relationships="store.relationships"
          />
          <ArtStyleSelector />
          <CharacterDesign
            v-if="store.characters.length"
            :characters="store.characters"
          />
        </div>
      </div>

      <button
        v-if="canGenerate"
        class="generate-btn"
        :disabled="!store.meta"
        @click="startGenerate"
      >
        {{ generateButtonLabel }}
      </button>

      <div v-if="error && !streaming && !hasSceneOutput" class="error-tip" role="alert" aria-live="assertive">{{ error }}</div>

      <div v-if="streaming || hasSceneOutput" class="script-section">
        <h2>剧本</h2>
        <div v-if="episodeCount" class="episode-slider">
          <button
            class="episode-nav-btn"
            :disabled="!canGoPrev"
            @click="goPrevEpisode"
          >
            ←
          </button>
          <div class="episode-slider-center">
            <div class="episode-slider-label">第 {{ currentEpisode?.episode }} 集 / 共 {{ episodeCount }} 集</div>
            <div class="episode-slider-title">{{ currentEpisode?.title || '未命名剧集' }}</div>
          </div>
          <button
            class="episode-nav-btn"
            :disabled="!canGoNext"
            @click="goNextEpisode"
          >
            →
          </button>
        </div>
        <SceneStream :scenes="currentEpisodeScenes" :streaming="streaming" />
        <div v-if="error" class="error-tip" role="alert" aria-live="assertive">{{ error }}</div>
        <div
          v-else-if="showIncompleteScriptTip"
          class="error-tip"
          role="alert"
          aria-live="assertive"
        >
          当前剧本不完整，请重新生成。
        </div>
      </div>

      <div v-if="done" class="btn-row">
        <button class="back-btn" @click="router.push('/step2')">← 返回</button>
        <button class="next-btn" @click="router.push('/step4')">预览导出 →</button>
      </div>
    </div>
  </div>
  <ApiKeyModal
    :show="showKeyModal"
    :type="keyModalType"
    :title="keyModalType === 'invalid' ? 'API Key 错误' : '未设置 API Key'"
    :message="keyModalMsg || '请先前往设置页填入 API Key，才能生成剧本。'"
    @close="showKeyModal = false"
  />
  <OutlineChatPanel :show="chatOpen" @close="chatOpen = false" />
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import StepIndicator from '../components/StepIndicator.vue'
import OutlinePreview from '../components/OutlinePreview.vue'
import SceneStream from '../components/SceneStream.vue'
import CharacterGraph from '../components/CharacterGraph.vue'
import CharacterDesign from '../components/CharacterDesign.vue'
import ApiKeyModal from '../components/ApiKeyModal.vue'
import OutlineChatPanel from '../components/OutlineChatPanel.vue'
import ArtStyleSelector from '../components/ArtStyleSelector.vue'
import { useStoryStore } from '../stores/story.js'
import { useSettingsStore } from '../stores/settings.js'
import { streamScript } from '../api/story.js'
import { canAccessStep, getStepRedirectPath } from '../utils/stepAccess.js'
import { cloneSerializable, formatEpisodeList, getIncompleteScriptEpisodes, hasCompleteGeneratedScript } from '../utils/scriptValidation.js'

const router = useRouter()
const store = useStoryStore()
const settings = useSettingsStore()
const streaming = ref(false)
const error = ref('')
const chatOpen = ref(false)
const showKeyModal = ref(false)
const keyModalType = ref('missing')
const keyModalMsg = ref('')
const currentEpisodeIndex = ref(0)
const userPinnedEpisode = ref(false)
const hasSceneOutput = computed(() => store.scenes.length > 0)
const hasValidScript = computed(() => hasCompleteGeneratedScript({
  outline: store.outline,
  scenes: store.scenes,
}))
const done = computed(() => store.step3Done && hasValidScript.value)
const canGenerate = computed(() => !streaming.value)
const generateButtonLabel = computed(() => (hasSceneOutput.value ? '重新生成剧本 ✨' : '开始生成剧本 ✨'))
const showIncompleteScriptTip = computed(() => (
  !streaming.value
  && hasSceneOutput.value
  && !hasValidScript.value
  && !error.value
))
const episodeCount = computed(() => store.scenes.length)
const currentEpisode = computed(() => store.scenes[currentEpisodeIndex.value] || null)
const currentEpisodeScenes = computed(() => (currentEpisode.value ? [currentEpisode.value] : []))
const canGoPrev = computed(() => currentEpisodeIndex.value > 0)
const canGoNext = computed(() => currentEpisodeIndex.value < episodeCount.value - 1)

let scriptAbortController = null
onUnmounted(() => { scriptAbortController?.abort() })
onMounted(() => {
  if (!canAccessStep(store, 3)) {
    router.replace(getStepRedirectPath(store, 3))
    return
  }
})

watch(
  () => store.scenes.length,
  (nextLength, previousLength = 0) => {
    if (!nextLength) {
      currentEpisodeIndex.value = 0
      userPinnedEpisode.value = false
      return
    }

    const shouldFollowLatest =
      !userPinnedEpisode.value ||
      previousLength === 0 ||
      currentEpisodeIndex.value >= previousLength - 1

    if (shouldFollowLatest) {
      currentEpisodeIndex.value = nextLength - 1
      return
    }

    currentEpisodeIndex.value = Math.min(currentEpisodeIndex.value, nextLength - 1)
  },
  { immediate: true }
)

function isAuthError(msg) {
  return /401|403|invalid|incorrect|unauthorized|api.?key/i.test(msg)
}

function captureScriptSnapshot() {
  const hasValidScript = hasCompleteGeneratedScript({
    outline: store.outline,
    scenes: store.scenes,
  })

  return {
    hasValidScript,
    scenes: cloneSerializable(store.scenes, []),
    meta: cloneSerializable(store.meta, null),
    sceneReferenceAssets: cloneSerializable(store.sceneReferenceAssets, {}),
    shots: cloneSerializable(store.shots, []),
    storyboardFinalVideoUrl: store.storyboardFinalVideoUrl || '',
    manualProjectId: store.manualProjectId || '',
    manualPipelineId: store.manualPipelineId || '',
    manualStoryId: store.manualStoryId || '',
  }
}

function rollbackScriptGeneration(snapshot, message) {
  if (snapshot?.hasValidScript) {
    store.meta = cloneSerializable(snapshot.meta, null)
    store.scenes = cloneSerializable(snapshot.scenes, [])
    store.sceneReferenceAssets = cloneSerializable(snapshot.sceneReferenceAssets, {})
    store.setShots(cloneSerializable(snapshot.shots, []))
    store.setStoryboardFinalVideoUrl(snapshot.storyboardFinalVideoUrl || '')
    store.setManualPipelineContext({
      projectId: snapshot.manualProjectId || '',
      pipelineId: snapshot.manualPipelineId || '',
      storyId: snapshot.manualStoryId || '',
    })
    store.step3Done = true
    store.ensureSceneReferenceAssets()
  } else {
    store.resetScenes()
    store.step3Done = false
  }

  store.setStep(3)
  error.value = message
}

async function startGenerate() {
  scriptAbortController?.abort()
  const controller = new AbortController()
  scriptAbortController = controller
  const previousScriptSnapshot = captureScriptSnapshot()
  const isOverwritingValidScript = previousScriptSnapshot.hasValidScript
  streaming.value = true
  error.value = ''
  currentEpisodeIndex.value = 0
  userPinnedEpisode.value = false
  store.resetScenes()
  try {
    await streamScript(
      store.storyId,
      (scene) => store.addScene(scene),
      () => {
      const isCompleteScript = hasCompleteGeneratedScript({
        outline: store.outline,
        scenes: store.scenes,
      })
      if (!isCompleteScript) {
        const incompleteEpisodes = getIncompleteScriptEpisodes({
          outline: store.outline,
          scenes: store.scenes,
        })
        const suffix = isOverwritingValidScript ? '，已回滚到上一次有效结果' : ''
        const message = incompleteEpisodes.length > 0
          ? `剧本生成不完整：${formatEpisodeList(incompleteEpisodes)} 未生成有效场景${suffix}`
          : `剧本生成失败：当前故事缺少大纲或返回结果结构无效，请重试${suffix}`
        rollbackScriptGeneration(
          previousScriptSnapshot,
          message
        )
        return
      }
      store.step3Done = true
      store.setStep(4)
      },
      (msg) => {
      const normalizedMessage = msg || '生成失败，请重试'
      rollbackScriptGeneration(
        previousScriptSnapshot,
        isOverwritingValidScript
          ? `${normalizedMessage}，已回滚到上一次有效结果`
          : normalizedMessage
      )
      if (isAuthError(msg)) {
        keyModalType.value = 'invalid'
        keyModalMsg.value = 'API Key 无效或已过期，请检查后重新设置。'
        showKeyModal.value = true
      }
    },
      controller.signal
    )
  } finally {
    streaming.value = false
    if (scriptAbortController === controller) {
      scriptAbortController = null
    }
  }
}

function goPrevEpisode() {
  if (!canGoPrev.value) return
  currentEpisodeIndex.value -= 1
  userPinnedEpisode.value = true
}

function goNextEpisode() {
  if (!canGoNext.value) return
  currentEpisodeIndex.value += 1
  userPinnedEpisode.value = currentEpisodeIndex.value < episodeCount.value - 1
}
</script>

<style scoped src="../style/step3script.css"></style>
