<template>
  <div class="page">
    <StepIndicator :current="2" :loading="submitting" />
    <div class="content">
      <h1>世界观构建</h1>
      <p class="subtitle">AI 将通过几轮提问帮你构建完整的故事世界观</p>

      <!-- 种子想法折叠卡片 -->
      <div class="idea-recap" @click="ideaExpanded = !ideaExpanded">
        <div class="recap-header">
          <div class="recap-meta">
            <span class="recap-label">你的灵感</span>
            <span v-if="store.input.genre" class="recap-tag">{{ store.input.genre }}</span>
          </div>
          <span class="recap-toggle">{{ ideaExpanded ? '▼' : '▲' }}</span>
        </div>
        <div v-if="ideaExpanded" class="recap-body">{{ store.input.idea }}</div>
      </div>

      <!-- 对话历史 -->
      <div class="chat-history" ref="historyEl">
        <div v-for="(msg, i) in store.wbHistory" :key="i" :class="['bubble', msg.role]">
          <div class="bubble-text">{{ msg.text }}</div>
        </div>
        <div v-if="submitting" class="bubble ai">
          <div class="bubble-text thinking">思考中...</div>
        </div>
      </div>

      <!-- 当前问题输入区 -->
      <div v-if="store.wbCurrentQuestion" class="input-area">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: `${(store.wbTurn / 6) * 100}%` }"></div>
        </div>
        <div class="progress-label">第 {{ store.wbTurn }} / 6 轮</div>

        <!-- 选项模式 -->
        <div v-if="store.wbCurrentQuestion.type === 'options'" class="options-group">
          <button
            v-for="opt in store.wbCurrentQuestion.options"
            :key="opt"
            class="opt-btn"
            :class="{ selected: answer === opt }"
            :disabled="submitting"
            @click="answer = opt; customAnswer = ''"
          >{{ opt }}</button>
        </div>

        <!-- 选项模式下的自定义输入 -->
        <textarea
          v-if="store.wbCurrentQuestion.type === 'options'"
          v-model="customAnswer"
          placeholder="或者自己输入..."
          rows="2"
          class="open-input"
          :disabled="submitting"
          @input="answer = customAnswer"
        />

        <!-- 开放模式 -->
        <textarea
          v-else
          v-model="answer"
          placeholder="请输入你的想法..."
          rows="3"
          class="open-input"
          :disabled="submitting"
        />

        <div class="btn-row">
          <button class="back-btn" :disabled="submitting" @click="router.push('/step1')">← 返回</button>
          <button class="submit-btn" :disabled="!answer.trim() || submitting" @click="submitTurn">
            提交回答 →
          </button>
        </div>
        <div v-if="error" class="error-tip">{{ error }}</div>
      </div>

      <!-- 完成状态 -->
      <div v-if="worldBuildingComplete" class="complete-area">
        <div class="complete-msg">{{ completeMessage }}</div>
        <div class="btn-row complete-btn-row">
          <button
            class="back-btn complete-secondary-btn"
            :disabled="submitting || !store.selectedSetting"
            @click="goToScriptStep"
          >
            前往剧本生成 →
          </button>
          <button
            class="submit-btn complete-action-btn"
            :disabled="submitting || !store.input.idea"
            @click="requestRestartWorldBuilding"
          >
            {{ restartWorldBuildingButtonLabel }}
          </button>
        </div>
        <div v-if="!store.selectedSetting" class="error-tip complete-error-tip">当前缺少世界观总结，暂时无法生成剧本。</div>
        <div v-else-if="error" class="error-tip complete-error-tip">{{ error }}</div>
      </div>
    </div>
  </div>
  <div v-if="showRestartConfirm" class="overlay" @click.self="closeRestartConfirm">
    <div class="confirm-box">
      <div class="confirm-title">确认重新构建世界观</div>
      <div class="confirm-msg">{{ restartConfirmMessage }}</div>
      <div class="confirm-actions">
        <button class="confirm-cancel" :disabled="submitting" @click="closeRestartConfirm">取消</button>
        <button class="confirm-ok" :disabled="submitting" @click="restartWorldBuilding">
          {{ activeAction === 'restart' ? '重新构建中...' : '确认重新构建' }}
        </button>
      </div>
    </div>
  </div>
  <ApiKeyModal
    :show="showKeyModal"
    :type="keyModalType"
    :title="keyModalType === 'invalid' ? 'API Key 错误' : '未设置 API Key'"
    :message="keyModalMsg || '请先前往设置页填入 API Key，才能继续。'"
    @close="showKeyModal = false"
  />
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import StepIndicator from '../components/StepIndicator.vue'
import ApiKeyModal from '../components/ApiKeyModal.vue'
import { useStoryStore } from '../stores/story.js'
import { worldBuildingStart, worldBuildingTurn } from '../api/story.js'

const router = useRouter()
const store = useStoryStore()

const answer = ref('')
const customAnswer = ref('')
const submitting = ref(false)
const error = ref('')
const ideaExpanded = ref(true)
const historyEl = ref(null)
const showKeyModal = ref(false)
const keyModalType = ref('missing')
const keyModalMsg = ref('')
const showRestartConfirm = ref(false)
const activeAction = ref('')
const worldBuildingComplete = computed(() => !store.wbCurrentQuestion && store.wbTurn > 0)
const completeMessage = computed(() => (
  '世界观构建完成，可前往剧本生成或重新构建世界观。'
))
const restartWorldBuildingButtonLabel = computed(() => (
  activeAction.value === 'restart' ? '重新构建中...' : '重新构建世界观'
))
const restartConfirmMessage = computed(() => {
  const parts = ['当前世界观问答']
  if (store.meta) parts.push('已生成的大纲')
  if (store.scenes?.length) parts.push('已生成的剧本')
  return `继续后将从第 1 轮重新开始，并清空${parts.join('、')}。此操作不可撤销，确定继续吗？`
})

function isAuthError(msg) {
  return /401|403|invalid|incorrect|unauthorized|api.?key/i.test(msg)
}

async function scrollToBottom() {
  await nextTick()
  if (historyEl.value) historyEl.value.scrollTop = historyEl.value.scrollHeight
}

watch(() => store.wbHistory.length, scrollToBottom)

function goToScriptStep() {
  if (!store.storyId || !store.selectedSetting) {
    error.value = '当前缺少世界观总结，暂时无法生成剧本。'
    return
  }
  error.value = ''
  store.setStep(3)
  router.push('/step3')
}

function closeRestartConfirm() {
  if (submitting.value) return
  showRestartConfirm.value = false
}

function requestRestartWorldBuilding() {
  if (!store.input.idea || submitting.value) return
  showRestartConfirm.value = true
}

async function restartWorldBuilding() {
  const inputIdea = String(store.input.idea || '').trim()
  const inputGenre = String(store.input.genre || '').trim()
  const inputTone = String(store.input.tone || '').trim()
  if (!inputIdea) {
    error.value = '当前缺少灵感内容，暂时无法重新构建世界观。'
    return
  }

  submitting.value = true
  activeAction.value = 'restart'
  error.value = ''
  try {
    showRestartConfirm.value = false
    const result = await worldBuildingStart(inputIdea, inputGenre)
    answer.value = ''
    customAnswer.value = ''
    store.startNewStory(inputIdea, inputGenre, inputTone)
    store.setWorldBuildingStart(result)
    store.setStep(2)
    ideaExpanded.value = true
    await scrollToBottom()
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
    submitting.value = false
    activeAction.value = ''
  }
}

async function submitTurn() {
  const userAnswer = answer.value.trim()
  if (!userAnswer) return
  submitting.value = true
  activeAction.value = 'turn'
  error.value = ''
  try {
    const result = await worldBuildingTurn(store.storyId, userAnswer)
    answer.value = ''
    customAnswer.value = ''
    store.appendWbTurn({ ...result, answer: userAnswer })
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
    submitting.value = false
    activeAction.value = ''
  }
}
</script>

<style scoped src="../style/step2settings.css"></style>
