<template>
  <div class="page">
    <StepIndicator :current="3" :loading="streaming" />
    <div class="content">
      <div class="title-row">
        <div>
          <h1>剧本生成</h1>
          <p class="subtitle">先确认集数，再开始生成完整剧本</p>
        </div>
      </div>

      <div v-if="showPostGenerationPanels" class="top-row">
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

      <div class="episode-count-card">
        <div class="episode-count-copy">
          <div class="episode-count-title">剧本集数</div>
          <div class="episode-count-subtitle">支持自定义集数。修改后，点击生成剧本会先按新集数重建大纲。</div>
        </div>
        <label class="episode-count-field">
          <span>集数</span>
          <input
            v-model="episodeCountInput"
            type="text"
            inputmode="numeric"
            class="episode-count-input"
            placeholder="请输入集数"
            :disabled="streaming"
          />
        </label>
      </div>

      <div
        v-if="episodeCountInputInvalid"
        class="error-tip episode-count-tip"
        role="alert"
        aria-live="assertive"
      >
        请输入大于 0 的整数集数。
      </div>
      <div
        v-else-if="episodeCountChanged && !streaming"
        class="resume-hint episode-count-tip"
        role="status"
        aria-live="polite"
      >
        {{ episodeCountHint }}
      </div>

      <div v-if="showResumeActionRow" class="generate-action-row">
        <button
          class="continue-btn"
          type="button"
          :disabled="nextIncompleteEpisode == null || !canSubmitEpisodeCount || episodeCountChanged"
          :title="resumeButtonHint"
          @click="startContinueGenerate"
        >
          {{ continueButtonLabel }}
        </button>
        <button
          class="generate-btn generate-btn-secondary"
          :disabled="!store.selectedSetting || !canSubmitEpisodeCount"
          @click="startGenerate"
        >
          {{ generateButtonLabel }}
        </button>
      </div>

      <div
        v-else-if="canGenerate"
        class="generate-btn-wrapper"
      >
        <button
          class="generate-btn"
          :disabled="!store.selectedSetting || !canSubmitEpisodeCount"
          @click="startGenerate"
        >
          {{ generateButtonLabel }}
        </button>
      </div>

      <div
        v-if="showResumeActionRow"
        class="resume-hint"
        role="status"
        aria-live="polite"
      >
        {{ resumeButtonHint }}
      </div>

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
          {{ showResumeActionRow ? '当前剧本不完整，可继续生成或重新生成全部。' : '当前剧本不完整，请重新生成。' }}
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
import { generateOutline, streamScript } from '../api/story.js'
import { canAccessStep, getStepRedirectPath } from '../utils/stepAccess.js'
import { formatEpisodeList, getIncompleteScriptEpisodes, hasCompleteGeneratedScript } from '../utils/scriptValidation.js'

function parsePositiveInteger(value) {
  const text = String(value ?? '').trim()
  if (!/^\d+$/.test(text)) return null
  const parsed = Number.parseInt(text, 10)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

function parseEpisodeCountInput(value) {
  return parsePositiveInteger(value)
}

const router = useRouter()
const store = useStoryStore()
const streaming = ref(false)
const error = ref('')
const chatOpen = ref(false)
const showKeyModal = ref(false)
const keyModalType = ref('missing')
const keyModalMsg = ref('')
const currentEpisodeIndex = ref(0)
const userPinnedEpisode = ref(false)
const episodeCountInput = ref('')
const hasSceneOutput = computed(() => store.scenes.length > 0)
const showPostGenerationPanels = computed(() => !streaming.value && hasSceneOutput.value)
const currentOutlineEpisodeCount = computed(() => (
  parsePositiveInteger(store.meta?.episodes) || parsePositiveInteger(store.outline.length) || null
))
const requestedEpisodeCount = computed(() => parseEpisodeCountInput(episodeCountInput.value))
const canSubmitEpisodeCount = computed(() => requestedEpisodeCount.value != null)
const episodeCountInputInvalid = computed(() => (
  episodeCountInput.value.trim().length > 0 && requestedEpisodeCount.value == null
))
const episodeCountChanged = computed(() => (
  currentOutlineEpisodeCount.value != null
  && requestedEpisodeCount.value != null
  && requestedEpisodeCount.value !== currentOutlineEpisodeCount.value
))
const generatedEpisodeNumbers = computed(() => store.scenes
  .filter(episode => Array.isArray(episode?.scenes) && episode.scenes.length > 0)
  .map(episode => {
    const parsed = Number.parseInt(String(episode?.episode ?? '').trim(), 10)
    return Number.isInteger(parsed) ? parsed : null
  })
  .filter(episode => episode != null)
  .sort((left, right) => left - right))
const lastGeneratedEpisode = computed(() => (
  generatedEpisodeNumbers.value.length > 0
    ? generatedEpisodeNumbers.value[generatedEpisodeNumbers.value.length - 1]
    : null
))
const hasValidScript = computed(() => hasCompleteGeneratedScript({
  outline: store.outline,
  scenes: store.scenes,
}))
const incompleteEpisodes = computed(() => getIncompleteScriptEpisodes({
  outline: store.outline,
  scenes: store.scenes,
}))
const nextIncompleteEpisode = computed(() => incompleteEpisodes.value[0] ?? null)
const done = computed(() => store.step3Done && hasValidScript.value)
const canGenerate = computed(() => !streaming.value)
const episodeCountHint = computed(() => {
  if (!episodeCountChanged.value || requestedEpisodeCount.value == null) return ''
  if (hasSceneOutput.value) {
    return `当前大纲是 ${currentOutlineEpisodeCount.value} 集，生成时会先更新为 ${requestedEpisodeCount.value} 集，并清空已生成剧本。`
  }
  return `当前大纲是 ${currentOutlineEpisodeCount.value} 集，生成时会先更新为 ${requestedEpisodeCount.value} 集并重新生成大纲。`
})
const generateButtonLabel = computed(() => {
  if (episodeCountChanged.value) {
    return hasSceneOutput.value ? '更新集数并重新生成剧本 ✨' : '按新集数生成剧本 ✨'
  }
  return hasSceneOutput.value ? '重新生成剧本 ✨' : '开始生成剧本 ✨'
})
const showResumeActionRow = computed(() => (
  canGenerate.value
  && hasSceneOutput.value
  && !hasValidScript.value
  && nextIncompleteEpisode.value != null
  && !episodeCountChanged.value
  && !episodeCountInputInvalid.value
))
const continueButtonLabel = computed(() => (
  nextIncompleteEpisode.value != null
    ? `继续生成（第 ${nextIncompleteEpisode.value} 集起）`
    : '继续生成'
))
const resumeButtonHint = computed(() => (
  nextIncompleteEpisode.value != null
    ? lastGeneratedEpisode.value != null
      ? `当前已保留到第 ${lastGeneratedEpisode.value} 集，可从第 ${nextIncompleteEpisode.value} 集继续生成；如需全部重做，也可以重新生成全部。`
      : `当前剧本在第 ${nextIncompleteEpisode.value} 集中断，可从该集继续生成。`
    : '当前剧本不完整，可继续生成或重新生成全部。'
))
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
  currentOutlineEpisodeCount,
  (nextValue) => {
    episodeCountInput.value = nextValue == null ? '' : String(nextValue)
  },
  { immediate: true }
)

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

function buildResumeErrorHint() {
  if (!store.scenes.length || nextIncompleteEpisode.value == null) return ''
  if (lastGeneratedEpisode.value != null) {
    return `已保留到第 ${lastGeneratedEpisode.value} 集，可从第 ${nextIncompleteEpisode.value} 集继续生成`
  }
  return `已保留已成功集数，可从第 ${nextIncompleteEpisode.value} 集继续生成`
}

function setScriptGenerationError(message) {
  store.setStep(3)
  store.step3Done = false
  const normalizedMessage = String(message || '生成失败，请重试').trim()
  const resumeHint = buildResumeErrorHint()
  error.value = resumeHint ? `${normalizedMessage}，${resumeHint}` : normalizedMessage
}

async function syncOutlineEpisodeCount() {
  const targetEpisodeCount = requestedEpisodeCount.value
  if (targetEpisodeCount == null) {
    throw new Error('请输入大于 0 的整数集数')
  }
  if (!store.storyId || !store.selectedSetting) {
    throw new Error('当前缺少世界观总结，请返回上一步确认后再生成剧本。')
  }
  if (targetEpisodeCount === currentOutlineEpisodeCount.value && store.outline.length === targetEpisodeCount) {
    return false
  }

  const outline = await generateOutline(store.storyId, store.selectedSetting, targetEpisodeCount)
  store.setOutlineResult(outline)
  store.setStep(3)
  currentEpisodeIndex.value = 0
  userPinnedEpisode.value = false
  return true
}

async function runGenerate({ resumeFromEpisode = null } = {}) {
  scriptAbortController?.abort()
  const controller = new AbortController()
  scriptAbortController = controller
  let isResumeGeneration = Number.isInteger(resumeFromEpisode)
  streaming.value = true
  error.value = ''
  userPinnedEpisode.value = false
  store.setStep(3)
  try {
    const outlineUpdated = await syncOutlineEpisodeCount()
    if (outlineUpdated) {
      isResumeGeneration = false
      resumeFromEpisode = null
    }

    if (isResumeGeneration) {
      store.retainScenesBeforeEpisode(resumeFromEpisode)
      currentEpisodeIndex.value = Math.max(store.scenes.length - 1, 0)
    } else {
      currentEpisodeIndex.value = 0
      store.resetScenes()
    }

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
          const message = incompleteEpisodes.length > 0
            ? `剧本生成不完整：${formatEpisodeList(incompleteEpisodes)} 未生成有效场景`
            : '剧本生成失败：当前故事缺少大纲或返回结果结构无效，请重试'
          setScriptGenerationError(message)
          return
        }
        error.value = ''
        store.step3Done = true
        store.setStep(4)
      },
      (msg) => {
        const normalizedMessage = msg || '生成失败，请重试'
        setScriptGenerationError(normalizedMessage)
        if (isAuthError(msg)) {
          keyModalType.value = 'invalid'
          keyModalMsg.value = 'API Key 无效或已过期，请检查后重新设置。'
          showKeyModal.value = true
        }
      },
      controller.signal,
      isResumeGeneration ? { resumeFromEpisode } : {}
    )
  } catch (e) {
    const msg = e.message || '生成失败，请重试'
    store.setStep(3)
    store.step3Done = false
    error.value = msg
    if (isAuthError(msg)) {
      keyModalType.value = 'invalid'
      keyModalMsg.value = 'API Key 无效或已过期，请检查后重新设置。'
      showKeyModal.value = true
    }
  } finally {
    streaming.value = false
    if (scriptAbortController === controller) {
      scriptAbortController = null
    }
  }
}

async function startGenerate() {
  await runGenerate()
}

async function startContinueGenerate() {
  if (episodeCountChanged.value || !canSubmitEpisodeCount.value) return
  if (nextIncompleteEpisode.value == null) return
  await runGenerate({ resumeFromEpisode: nextIncompleteEpisode.value })
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
