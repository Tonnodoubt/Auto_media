<template>
  <div class="page">
    <StepIndicator :current="2" :loading="submitting" />
    <div class="content">
      <h1>世界观构建</h1>
      <p class="subtitle">AI 将通过几轮提问帮你构建完整的故事世界观</p>

      <!-- 种子想法折叠卡片 -->
      <div class="idea-recap" @click="ideaExpanded = !ideaExpanded">
        <div class="recap-header">
          <span class="recap-label">你的灵感</span>
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
      <div v-if="complete || (!store.wbCurrentQuestion && store.wbTurn > 0)" class="complete-area">
        <div class="complete-msg">{{ store.meta ? '世界观构建完成！' : '世界观构建完成，正在生成大纲...' }}</div>
        <button v-if="store.meta && !submitting" class="submit-btn" style="margin-top: 12px" @click="router.push('/step3')">前往剧本生成 →</button>
        <button v-if="error && !submitting && !store.meta" class="submit-btn" style="margin-top: 12px" @click="retryOutline">重试生成大纲</button>
        <div v-if="error" class="error-tip" style="margin-top: 8px">{{ error }}</div>
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
import { ref, watch, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import StepIndicator from '../components/StepIndicator.vue'
import ApiKeyModal from '../components/ApiKeyModal.vue'
import { useStoryStore } from '../stores/story.js'
import { useSettingsStore } from '../stores/settings.js'
import { worldBuildingTurn, generateOutline } from '../api/story.js'

const router = useRouter()
const store = useStoryStore()
const settings = useSettingsStore()

const answer = ref('')
const customAnswer = ref('')
const submitting = ref(false)
const complete = ref(false)
const error = ref('')
const ideaExpanded = ref(true)
const historyEl = ref(null)
const showKeyModal = ref(false)
const keyModalType = ref('missing')
const keyModalMsg = ref('')

function isAuthError(msg) {
  return /401|403|invalid|incorrect|unauthorized|api.?key/i.test(msg)
}

async function scrollToBottom() {
  await nextTick()
  if (historyEl.value) historyEl.value.scrollTop = historyEl.value.scrollHeight
}

watch(() => store.wbHistory.length, scrollToBottom)

onMounted(async () => {
  // World building completed but outline generation was interrupted (e.g., user opened settings mid-flight)
  // wbCurrentQuestion is null (no more questions) and meta not yet set → retry generateOutline
  if (!store.wbCurrentQuestion && store.wbTurn > 0 && store.selectedSetting && !store.meta) {
    complete.value = true
    submitting.value = true
    try {
      const outline = await generateOutline(store.storyId, store.selectedSetting)
      store.setOutlineResult(outline)
      store.setStep(3)
      router.push('/step3')
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
    }
  }
})

async function retryOutline() {
  submitting.value = true
  error.value = ''
  try {
    const outline = await generateOutline(store.storyId, store.selectedSetting)
    store.setOutlineResult(outline)
    store.setStep(3)
    router.push('/step3')
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
  }
}

async function submitTurn() {
  const userAnswer = answer.value.trim()
  if (!userAnswer) return
  submitting.value = true
  error.value = ''
  try {
    const result = await worldBuildingTurn(store.storyId, userAnswer)
    answer.value = ''
    customAnswer.value = ''
    store.appendWbTurn({ ...result, answer: userAnswer })
    if (result.status === 'complete') {
      complete.value = true
      const outline = await generateOutline(store.storyId, result.world_summary)
      store.setOutlineResult(outline)
      store.setStep(3)
      router.push('/step3')
    }
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
  }
}
</script>

<style scoped>
.page { min-height: 100vh; background: #f5f5f7; padding: 32px 16px; }
.content { max-width: 600px; margin: 32px auto 0; display: flex; flex-direction: column; gap: 16px; }
h1 { font-size: 26px; font-weight: 700; margin-bottom: 6px; }
.subtitle { color: #888; margin-bottom: 8px; }

.idea-recap {
  background: #fff;
  border-radius: 12px;
  padding: 12px 16px;
  border-left: 4px solid #6c63ff;
  cursor: pointer;
  user-select: none;
}
.recap-header { display: flex; justify-content: space-between; align-items: center; }
.recap-label { font-size: 13px; font-weight: 600; color: #6c63ff; }
.recap-toggle { font-size: 11px; color: #aaa; }
.recap-body { margin-top: 8px; font-size: 14px; color: #555; line-height: 1.6; }

.chat-history {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 360px;
  overflow-y: auto;
  padding: 4px 0;
}
.bubble { max-width: 85%; }
.bubble.ai { align-self: flex-start; }
.bubble.user { align-self: flex-end; }
.bubble-text {
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.6;
}
.bubble.ai .bubble-text { background: #fff; color: #333; border-bottom-left-radius: 4px; }
.bubble.user .bubble-text { background: #6c63ff; color: #fff; border-bottom-right-radius: 4px; }
.thinking { color: #aaa; font-style: italic; }

.input-area { display: flex; flex-direction: column; gap: 12px; }
.progress-bar { height: 4px; background: #e0e0e0; border-radius: 2px; }
.progress-fill { height: 100%; background: #6c63ff; border-radius: 2px; transition: width 0.4s; }
.progress-label { font-size: 12px; color: #aaa; text-align: right; margin-top: -8px; }

.options-group { display: flex; gap: 8px; flex-wrap: wrap; }
.opt-btn {
  padding: 10px 18px;
  border-radius: 20px;
  background: #fff;
  border: 2px solid #e0e0e0;
  font-size: 14px;
  color: #555;
  cursor: pointer;
  transition: all 0.2s;
}
.opt-btn:hover { border-color: #6c63ff; color: #6c63ff; }
.opt-btn.selected { border-color: #6c63ff; background: #f0eeff; color: #6c63ff; font-weight: 600; }
.opt-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.open-input {
  width: 100%;
  padding: 12px 16px;
  border-radius: 12px;
  border: 2px solid #e0e0e0;
  font-size: 14px;
  resize: none;
  line-height: 1.6;
  font-family: inherit;
  transition: border-color 0.2s;
}
.open-input:focus { border-color: #6c63ff; outline: none; }
.open-input:disabled { background: #f9f9f9; color: #999; cursor: not-allowed; }

.btn-row { display: flex; gap: 12px; }
.back-btn {
  padding: 12px 18px;
  background: #fff;
  color: #555;
  border-radius: 12px;
  font-size: 14px;
  border: 2px solid #e0e0e0;
  cursor: pointer;
}
.back-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.submit-btn {
  flex: 1;
  padding: 12px;
  background: #6c63ff;
  color: #fff;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}
.submit-btn:hover:not(:disabled) { background: #5a52e0; }
.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.complete-area { text-align: center; padding: 24px; }
.complete-msg { color: #6c63ff; font-size: 15px; font-weight: 600; }
.error-tip { color: #e53935; font-size: 13px; text-align: center; }
</style>
