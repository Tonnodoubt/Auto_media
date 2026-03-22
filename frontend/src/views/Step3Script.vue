<template>
  <div class="page">
    <StepIndicator :current="3" />
    <div class="content">
      <div class="title-row">
        <div>
          <h1>剧本生成</h1>
          <p class="subtitle">确认大纲后开始生成完整剧本</p>
        </div>
        <button class="chat-toggle-btn" @click="chatOpen = true">✦ AI 修改助手</button>
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
          <CharacterDesign
            v-if="store.characters.length"
            :characters="store.characters"
          />
        </div>
      </div>

      <button
        v-if="!started"
        class="generate-btn"
        :disabled="!store.meta"
        @click="startGenerate"
      >
        开始生成剧本 ✨
      </button>

      <div v-if="started" class="script-section">
        <h2>剧本</h2>
        <SceneStream :scenes="store.scenes" :streaming="streaming" />
        <div v-if="error" class="error-tip">{{ error }}</div>
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
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import StepIndicator from '../components/StepIndicator.vue'
import OutlinePreview from '../components/OutlinePreview.vue'
import SceneStream from '../components/SceneStream.vue'
import CharacterGraph from '../components/CharacterGraph.vue'
import CharacterDesign from '../components/CharacterDesign.vue'
import ApiKeyModal from '../components/ApiKeyModal.vue'
import OutlineChatPanel from '../components/OutlineChatPanel.vue'
import { useStoryStore } from '../stores/story.js'
import { useSettingsStore } from '../stores/settings.js'
import { streamScript } from '../api/story.js'

const router = useRouter()
const store = useStoryStore()
const settings = useSettingsStore()
const started = ref(false)
const streaming = ref(false)
const done = ref(false)
const error = ref('')
const chatOpen = ref(false)
const showKeyModal = ref(false)
const keyModalType = ref('missing')
const keyModalMsg = ref('')

function isAuthError(msg) {
  return /401|403|invalid|incorrect|unauthorized|api.?key/i.test(msg)
}

async function startGenerate() {
  if (!settings.useMock && !settings.effectiveLlmApiKey) { showKeyModal.value = true; return }
  started.value = true
  streaming.value = true
  error.value = ''
  store.resetScenes()
  await streamScript(
    store.storyId,
    (scene) => store.addScene(scene),
    () => { streaming.value = false; done.value = true; store.setStep(4) },
    (msg) => {
      streaming.value = false
      if (isAuthError(msg)) {
        keyModalType.value = 'invalid'
        keyModalMsg.value = 'API Key 无效或已过期，请检查后重新设置。'
        showKeyModal.value = true
      } else {
        error.value = msg || '生成失败，请重试'
      }
    }
  )
}
</script>

<style scoped>
.page { min-height: 100vh; background: #f5f5f7; padding: 32px 16px; }
.content { max-width: 900px; margin: 32px auto 0; }
.title-row { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
h1 { font-size: 26px; font-weight: 700; margin-bottom: 6px; }
.subtitle { color: #888; }
.chat-toggle-btn {
  padding: 10px 18px;
  background: linear-gradient(135deg, #6c63ff, #a78bfa);
  color: #fff;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.2s;
}
.chat-toggle-btn:hover { opacity: 0.9; }
.top-row { display: flex; gap: 16px; align-items: flex-start; }
.outline-col { flex: 1; min-width: 0; }
.graph-col { width: 380px; flex-shrink: 0; position: sticky; top: 24px; }
.generate-btn {
  margin-top: 24px;
  width: 100%;
  padding: 16px;
  background: linear-gradient(135deg, #6c63ff, #a78bfa);
  color: #fff;
  border-radius: 14px;
  font-size: 16px;
  font-weight: 600;
  transition: opacity 0.2s;
}
.generate-btn:hover:not(:disabled) { opacity: 0.9; }
.generate-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.script-section { margin-top: 28px; }
.script-section h2 { font-size: 18px; font-weight: 700; margin-bottom: 16px; }
.btn-row { display: flex; gap: 12px; margin-top: 28px; }
.back-btn {
  padding: 14px 20px;
  background: #fff;
  color: #555;
  border-radius: 12px;
  font-size: 15px;
  border: 2px solid #e0e0e0;
}
.next-btn {
  flex: 1;
  padding: 14px;
  background: #6c63ff;
  color: #fff;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
}
.next-btn:hover { background: #5a52e0; }
.error-tip { margin-top: 12px; color: #e53935; font-size: 13px; text-align: center; }
</style>
