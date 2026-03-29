<template>
  <div class="page">
    <StepIndicator :current="1" :loading="loading" />
    <div class="content">
      <h1>输入你的灵感</h1>
      <p class="subtitle">一句话描述你的故事创意，越具体生成越准</p>

      <div class="inspire-box">
        <textarea
          v-model="idea"
          placeholder="例如：一个失忆的女孩在陌生城市遇到了一个神秘男人..."
          rows="4"
        />
        <div class="hint" :class="{ warn: idea.length > 0 && idea.length < 15 }">
          {{ idea.length < 15 && idea.length > 0 ? '再多说一点，比如主角名字或关键场景，效果更好' : `${idea.length} 字` }}
        </div>
        <button class="toggle-gen-btn" @click="showGenerator = !showGenerator">
          {{ showGenerator ? '▲ 收起生成器' : '🎲 组合灵感生成器' }}
        </button>
      </div>

      <IdeaGenerator v-if="showGenerator" @apply="applyIdea" />

      <button class="next-btn" :disabled="!idea.trim() || loading" @click="submit">
        {{ loading ? '分析中...' : '开始构建世界观 →' }}
      </button>
      <button class="history-btn" @click="router.push('/history')" :disabled="loading">
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
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import StepIndicator from '../components/StepIndicator.vue'
import ApiKeyModal from '../components/ApiKeyModal.vue'
import IdeaGenerator from '../components/IdeaGenerator.vue'
import { useStoryStore } from '../stores/story.js'
import { useSettingsStore } from '../stores/settings.js'
import { worldBuildingStart } from '../api/story.js'

const router = useRouter()
const store = useStoryStore()
const settings = useSettingsStore()

const loading = ref(false)
const idea = ref(store.input.idea || '')
watch(idea, (val) => { store.input.idea = val })
const error = ref('')
const showGenerator = ref(false)
const showKeyModal = ref(false)
const keyModalType = ref('missing')
const keyModalMsg = ref('')

function applyIdea(text) {
  idea.value = text
}

function isAuthError(msg) {
  return /401|403|invalid|incorrect|unauthorized|api.?key/i.test(msg)
}

async function submit() {
  loading.value = true
  error.value = ''
  const inputIdea = idea.value.trim()
  try {
    const result = await worldBuildingStart(inputIdea)
    store.startNewStory(inputIdea)
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

<style scoped>
.page { min-height: 100vh; background: #f5f5f7; padding: 32px 16px; }
.content { max-width: 600px; margin: 32px auto 0; display: flex; flex-direction: column; gap: 16px; }
h1 { font-size: 26px; font-weight: 700; margin-bottom: 6px; }
.subtitle { color: #888; margin-bottom: 0; }
.inspire-box { display: flex; flex-direction: column; gap: 6px; }
textarea {
  width: 100%;
  padding: 16px;
  border-radius: 14px;
  border: 2px solid #e0e0e0;
  font-size: 15px;
  resize: none;
  background: #fff;
  transition: border-color 0.2s;
  line-height: 1.6;
  font-family: inherit;
}
textarea:focus { border-color: #6c63ff; outline: none; }
.hint { font-size: 12px; color: #aaa; text-align: right; }
.hint.warn { color: #f59e0b; }
.toggle-gen-btn {
  align-self: flex-start;
  padding: 8px 16px;
  background: #f0eeff;
  color: #6c63ff;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}
.toggle-gen-btn:hover { background: #e0d9ff; }
.next-btn {
  width: 100%;
  padding: 16px;
  background: #6c63ff;
  color: #fff;
  border-radius: 14px;
  font-size: 16px;
  font-weight: 600;
  transition: background 0.2s;
}
.next-btn:hover:not(:disabled) { background: #5a52e0; }
.next-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.history-btn {
  width: 100%;
  padding: 14px;
  background: #fff;
  color: #6c63ff;
  border-radius: 14px;
  font-size: 15px;
  font-weight: 600;
  border: 2px solid #e0e0e0;
  cursor: pointer;
  transition: border-color 0.2s;
}
.history-btn:hover:not(:disabled) { border-color: #6c63ff; }
.history-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.error-tip { color: #e53935; font-size: 13px; text-align: center; }
</style>
