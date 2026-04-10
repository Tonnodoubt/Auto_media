<template>
  <div class="page">
    <StepIndicator :current="1" :loading="loading || rewriteLoading" />
    <div class="content">
      <h1>输入你的灵感</h1>
      <p class="subtitle">写下一句话故事灵感，人物、冲突越清楚，越容易生成有短剧感的内容；如果还不够抓人，也可以先让 AI 帮你优化一下。</p>

      <div class="idea-dock">
        <div class="inspire-box">
          <textarea
            v-model="idea"
            placeholder="例如：一个失忆的女孩在陌生城市遇到了一个神秘男人..."
            rows="4"
          />
          <div class="hint" :class="{ warn: idea.length > 0 && idea.length < 15 }">
            {{ idea.length < 15 && idea.length > 0 ? '再多说一点，比如主角名字或关键场景，效果更好' : `${idea.length} 字` }}
          </div>
          <div class="tool-toggle-row">
            <button class="toggle-gen-btn" :disabled="loading || rewriteLoading" @click="showGenerator = !showGenerator">
              {{ showGenerator ? '▲ 收起生成器' : (normalizedGenre ? `🎲 组合灵感生成器 · ${normalizedGenre}` : '🎲 组合灵感生成器') }}
            </button>
            <button class="toggle-gen-btn" :disabled="loading || rewriteLoading" @click="showRewrite = !showRewrite">
              {{ showRewrite ? '▲ 收起AI修改灵感' : '✨ AI修改灵感' }}
            </button>
          </div>
        </div>
      </div>

      <IdeaGenerator
        v-if="showGenerator"
        v-model:selected-genre-key="selectedGenreKey"
        v-model:custom-genre="customGenre"
        :genre-options="genreOptions"
        :custom-genre-key="CUSTOM_GENRE_KEY"
        @apply="applyIdea"
      />

      <div v-if="showRewrite" class="rewrite-card">
        <div class="rewrite-header">
          <div>
            <div class="rewrite-title">AI修改灵感</div>
            <div class="rewrite-subtitle">描述你想怎么改，系统会先生成一版短剧感增强版供你确认；如果已选择故事题材，也会尽量按该方向收束。</div>
          </div>
          <div v-if="hasPendingRewrite" class="rewrite-round">待确认预览</div>
          <div v-else-if="rewriteHistory.length" class="rewrite-round">已采用 {{ rewriteHistory.length }} 轮</div>
        </div>

        <textarea
          v-model="rewriteInstruction"
          class="rewrite-instruction"
          placeholder="例如：主角动机更清楚，冲突更强，但不要改题材和人物关系。"
          rows="3"
          :disabled="loading || rewriteLoading"
        />
        <div class="rewrite-tip">每一轮都会基于当前输入框中的灵感生成一版短剧感增强版预览；如已选择题材，也会一起作为约束。确认后才会替换当前内容。</div>

        <div class="rewrite-actions">
          <button class="rewrite-btn" :disabled="!canRewrite || loading || rewriteLoading" @click="runRewrite">
            {{ rewriteLoading ? '生成中...' : (hasPendingRewrite ? '重新生成预览' : (rewriteHistory.length ? '再生成一版' : '生成增强版预览')) }}
          </button>
          <button class="rewrite-secondary-btn" :disabled="!canUndoRewrite || loading || rewriteLoading" @click="undoRewrite">
            撤销上一轮
          </button>
          <button class="rewrite-secondary-btn" :disabled="!canRestoreOriginal || loading || rewriteLoading" @click="restoreOriginalIdea">
            恢复原始灵感
          </button>
        </div>

        <div v-if="rewriteError" class="error-tip">{{ rewriteError }}</div>
        <div v-if="rewriteGuardrailNotice" class="guardrail-note">{{ rewriteGuardrailNotice }}</div>

        <div v-if="hasPendingRewrite" class="rewrite-result-card">
          <div class="preview-top">
            <div class="section-label">短剧感增强版预览</div>
            <span class="preview-round">第 {{ pendingRewriteRound }} 轮</span>
          </div>
          <div v-if="pendingRewriteInstruction" class="preview-instruction">修改要求：{{ pendingRewriteInstruction }}</div>
          <div v-if="pendingRewriteReason" class="preview-reason">增强说明：{{ pendingRewriteReason }}</div>
          <div class="section-text">{{ pendingRewriteIdea }}</div>
          <div class="preview-actions">
            <button class="rewrite-btn" :disabled="loading || rewriteLoading" @click="applyPendingRewrite">
              采用这版
            </button>
            <button class="rewrite-secondary-btn" :disabled="loading || rewriteLoading" @click="discardPendingRewrite">
              保留原文
            </button>
          </div>
        </div>

        <div v-if="rewriteHistory.length" class="history-section">
          <div class="section-label">改写历史</div>
          <div class="history-list">
            <div v-for="entry in rewriteHistory.slice().reverse()" :key="entry.round" class="history-card">
              <div class="history-top">
                <span class="history-round">第 {{ entry.round }} 轮</span>
                <span class="history-label">{{ entry.label }}</span>
              </div>
              <div class="history-instruction">修改要求：{{ entry.instruction }}</div>
              <div v-if="entry.reason" class="history-reason">增强说明：{{ entry.reason }}</div>
              <div class="history-text">{{ entry.text }}</div>
            </div>
          </div>
        </div>
      </div>

      <button class="next-btn" :disabled="!canSubmit || loading || rewriteLoading" @click="submit">
        {{ loading ? '分析中...' : '开始构建世界观 →' }}
      </button>
      <button class="history-btn" @click="router.push('/history')" :disabled="loading || rewriteLoading">
        查看历史剧本
      </button>
      <div v-if="error" class="error-tip">{{ error }}</div>
    </div>
  </div>
  <ApiKeyModal
    :show="showKeyModal"
    :type="keyModalType"
    :title="keyModalType === 'invalid' ? 'API Key 错误' : '未设置 API Key'"
    :message="keyModalMsg || '请先前往设置页填入 API Key，才能开始使用。'"
    @close="showKeyModal = false"
  />
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import StepIndicator from '../components/StepIndicator.vue'
import ApiKeyModal from '../components/ApiKeyModal.vue'
import IdeaGenerator from '../components/IdeaGenerator.vue'
import { useStoryStore } from '../stores/story.js'
import { rewriteIdea, worldBuildingStart } from '../api/story.js'

const router = useRouter()
const store = useStoryStore()
const CUSTOM_GENRE_KEY = '其他'
const presetGenreOptions = ['现代都市', '古装言情', '豪门恩怨', '复仇逆袭', '悬疑推理', '校园青春', '职场情感', '奇幻脑洞', '民国传奇', '末日生存']
const genreOptions = [...presetGenreOptions, CUSTOM_GENRE_KEY]
const initialGenre = String(store.input.genre || '').trim()

const loading = ref(false)
const idea = ref(store.input.idea || '')
const selectedGenreKey = ref(initialGenre ? (presetGenreOptions.includes(initialGenre) ? initialGenre : CUSTOM_GENRE_KEY) : '')
const customGenre = ref(initialGenre && !presetGenreOptions.includes(initialGenre) ? initialGenre : '')

const error = ref('')
const showGenerator = ref(false)
const showRewrite = ref(false)
const rewriteLoading = ref(false)
const rewriteInstruction = ref('')
const rewriteError = ref('')
const rewriteGuardrailNotice = ref('')
const rewriteHistory = ref([])
const rewriteSnapshots = ref([])
const originalIdea = ref('')
const pendingRewriteIdea = ref('')
const pendingRewriteReason = ref('')
const pendingRewriteInstruction = ref('')
const pendingRewriteRound = ref(0)
const pendingRewriteSourceIdea = ref('')
const showKeyModal = ref(false)
const keyModalType = ref('missing')
const keyModalMsg = ref('')

const normalizedGenre = computed(() => {
  if (selectedGenreKey.value === CUSTOM_GENRE_KEY) {
    return customGenre.value.trim()
  }
  return String(selectedGenreKey.value || '').trim()
})
const isGenreValid = computed(() => selectedGenreKey.value !== CUSTOM_GENRE_KEY || Boolean(customGenre.value.trim()))
const canRewrite = computed(() => idea.value.trim().length >= 10 && rewriteInstruction.value.trim().length > 0 && isGenreValid.value)
const canUndoRewrite = computed(() => rewriteSnapshots.value.length > 0)
const canRestoreOriginal = computed(() => Boolean(originalIdea.value.trim()) && idea.value.trim() !== originalIdea.value.trim())
const hasPendingRewrite = computed(() => Boolean(pendingRewriteIdea.value.trim()))
const canSubmit = computed(() => Boolean(idea.value.trim()) && isGenreValid.value && !hasPendingRewrite.value)

watch(idea, (val) => {
  store.input.idea = val
  if (!hasPendingRewrite.value) return

  const currentIdea = val.trim()
  if (!currentIdea) {
    discardPendingRewrite()
    return
  }

  if (
    currentIdea !== pendingRewriteSourceIdea.value.trim()
    && currentIdea !== pendingRewriteIdea.value.trim()
  ) {
    discardPendingRewrite()
  }
})

watch([selectedGenreKey, customGenre], () => {
  store.input.genre = normalizedGenre.value
  if (hasPendingRewrite.value) {
    discardPendingRewrite()
  }
})

function applyIdea(text) {
  idea.value = text
  rewriteHistory.value = []
  rewriteSnapshots.value = []
  originalIdea.value = ''
  clearRewriteFeedback()
}

function isAuthError(msg) {
  return /401|403|invalid|incorrect|unauthorized|api.?key/i.test(msg)
}

function ensureGenreConstraint(target = 'submit') {
  if (selectedGenreKey.value === CUSTOM_GENRE_KEY && !customGenre.value.trim()) {
    const message = '你选择了“其他”，请先补充具体的故事题材。'
    if (target === 'rewrite') {
      rewriteError.value = message
    } else {
      error.value = message
    }
    return false
  }
  return true
}

function clearRewriteFeedback() {
  rewriteError.value = ''
  rewriteGuardrailNotice.value = ''
  clearPendingRewrite()
}

function clearPendingRewrite() {
  pendingRewriteIdea.value = ''
  pendingRewriteReason.value = ''
  pendingRewriteInstruction.value = ''
  pendingRewriteRound.value = 0
  pendingRewriteSourceIdea.value = ''
}

function clearRewriteSession({ keepOriginal = true } = {}) {
  clearRewriteFeedback()
  rewriteHistory.value = []
  rewriteSnapshots.value = []
  if (!keepOriginal) originalIdea.value = ''
}

function undoRewrite() {
  if (!rewriteSnapshots.value.length) return
  const previousIdea = rewriteSnapshots.value.pop()
  const removedEntry = rewriteHistory.value.pop()
  clearRewriteFeedback()
  if (removedEntry?.instruction) rewriteInstruction.value = removedEntry.instruction
  idea.value = previousIdea
  if (!rewriteHistory.value.length) {
    originalIdea.value = previousIdea
  }
}

function restoreOriginalIdea() {
  if (!originalIdea.value.trim()) return
  clearRewriteSession({ keepOriginal: true })
  rewriteInstruction.value = ''
  idea.value = originalIdea.value
}

function applyPendingRewrite() {
  const rewrittenIdea = pendingRewriteIdea.value.trim()
  if (!rewrittenIdea) return

  const currentIdea = idea.value.trim()
  if (!currentIdea) {
    rewriteError.value = '当前灵感为空，暂时无法采用这版改写。'
    return
  }

  if (!originalIdea.value.trim()) {
    originalIdea.value = currentIdea
  }

  rewriteSnapshots.value.push(currentIdea)
  rewriteHistory.value.push({
    round: pendingRewriteRound.value || (rewriteHistory.value.length + 1),
    instruction: pendingRewriteInstruction.value || rewriteInstruction.value.trim(),
    label: '短剧感增强版',
    reason: pendingRewriteReason.value,
    text: rewrittenIdea,
  })

  rewriteError.value = ''
  error.value = ''
  idea.value = rewrittenIdea
  clearPendingRewrite()
}

function discardPendingRewrite() {
  error.value = ''
  rewriteError.value = ''
  rewriteGuardrailNotice.value = ''
  clearPendingRewrite()
}

async function runRewrite() {
  const currentIdea = idea.value.trim()
  const instruction = rewriteInstruction.value.trim()
  const currentGenre = normalizedGenre.value
  const currentOriginalIdea = originalIdea.value.trim() || currentIdea

  if (!currentIdea) {
    rewriteError.value = '请先输入灵感，再让 AI 帮你改写。'
    return
  }
  if (currentIdea.length < 10) {
    rewriteError.value = '请先把灵感写得更完整一些，再让 AI 改写。'
    return
  }
  if (!instruction) {
    rewriteError.value = '请先告诉 AI 你想怎么修改这段灵感。'
    return
  }
  if (!ensureGenreConstraint('rewrite')) {
    return
  }

  rewriteLoading.value = true
  clearRewriteFeedback()

  try {
    const round = rewriteHistory.value.length + 1
    const result = await rewriteIdea(
      currentOriginalIdea,
      currentIdea,
      instruction,
      round,
      currentGenre,
    )
    const rewrittenIdea = String(result.rewritten_idea || '').trim()
    if (!rewrittenIdea) {
      rewriteError.value = 'AI 暂未返回可用改写，请重试。'
      return
    }
    if (
      idea.value.trim() !== currentIdea
      || normalizedGenre.value !== currentGenre
      || rewriteInstruction.value.trim() !== instruction
      || (originalIdea.value.trim() || idea.value.trim()) !== currentOriginalIdea
    ) {
      rewriteError.value = '这次改写结果已过期，你在等待期间更新了灵感、题材或修改要求，请重新生成预览。'
      return
    }

    pendingRewriteIdea.value = rewrittenIdea
    pendingRewriteReason.value = String(result.rewrite_reason || '').trim()
    pendingRewriteInstruction.value = instruction
    pendingRewriteRound.value = Number(result.round) || round
    pendingRewriteSourceIdea.value = currentIdea
    rewriteGuardrailNotice.value = result.guardrail_notice || ''
  } catch (e) {
    const msg = e.message || '请求失败'
    if (isAuthError(msg)) {
      keyModalType.value = 'invalid'
      keyModalMsg.value = 'API Key 无效或已过期，请检查后重新设置。'
      showKeyModal.value = true
    } else {
      rewriteError.value = msg
    }
  } finally {
    rewriteLoading.value = false
  }
}

async function submit() {
  const inputIdea = idea.value.trim()
  const inputGenre = normalizedGenre.value
  error.value = ''
  if (hasPendingRewrite.value) {
    error.value = '你有一版待确认的短剧感增强版预览，请先选择“采用这版”或“保留原文”。'
    return
  }
  if (!ensureGenreConstraint('submit')) {
    return
  }

  loading.value = true
  try {
    const result = await worldBuildingStart(inputIdea, inputGenre)
    store.startNewStory(inputIdea, inputGenre)
    store.setWorldBuildingStart(result)
    store.setStep(2)
    router.push('/step2')
  } catch (e) {
    const msg = e.message || '请求失败'
    if (isAuthError(msg)) {
      keyModalType.value = 'invalid'
      keyModalMsg.value = 'API Key 无效或已过期，请检查后重新设置。'
      showKeyModal.value = true
    } else {
      error.value = msg
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped src="../style/step1inspire.css"></style>
