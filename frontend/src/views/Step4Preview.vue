<template>
  <div class="page">
    <StepIndicator :current="4" :loading="false" />
    <div class="content">
      <h1>预览 & 导出</h1>
      <p class="subtitle">你的短剧剧本已生成完毕</p>

      <div v-if="store.meta" class="summary-card">
        <div class="summary-title">{{ store.meta.title }}</div>
        <div class="summary-stats">
          <span>{{ store.meta.episodes }} 集</span>
          <span>{{ store.characters.length }} 个角色</span>
          <span>{{ totalScenes }} 个场景</span>
        </div>
      </div>

      <SceneStream :scenes="store.scenes" :streaming="false" />

      <div class="export-section">
        <ExportPanel />
        <button class="video-btn" @click="generateVideo">
          场景分镜
        </button>
        <button class="restart-btn" @click="restart">重新创作</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import StepIndicator from '../components/StepIndicator.vue'
import SceneStream from '../components/SceneStream.vue'
import ExportPanel from '../components/ExportPanel.vue'
import { useStoryStore } from '../stores/story.js'

const router = useRouter()
const store = useStoryStore()

onMounted(() => {
  if (!store.meta || !store.scenes.length) router.replace('/step1')
})

const totalScenes = computed(() =>
  store.scenes.reduce((sum, s) => sum + s.scenes.length, 0)
)

function generateVideo() {
  router.push('/video-generation')
}

function restart() {
  store.$reset()
  router.push('/step1')
}
</script>

<style scoped>
.page { min-height: 100vh; background: #f5f5f7; padding: 32px 16px; }
.content { max-width: 600px; margin: 32px auto 0; }
h1 { font-size: 26px; font-weight: 700; margin-bottom: 6px; }
.subtitle { color: #888; margin-bottom: 24px; }
.summary-card {
  background: linear-gradient(135deg, #6c63ff, #a78bfa);
  color: #fff;
  border-radius: 16px;
  padding: 20px;
  margin-bottom: 24px;
}
.summary-title { font-size: 20px; font-weight: 700; margin-bottom: 12px; }
.summary-stats { display: flex; gap: 16px; }
.summary-stats span {
  background: rgba(255,255,255,0.2);
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 13px;
}
.export-section {
  display: flex;
  gap: 12px;
  margin-top: 28px;
  align-items: center;
}
.video-btn {
  padding: 12px 20px;
  background: #6c63ff;
  color: #fff;
  border-radius: 10px;
  font-size: 14px;
  border: none;
  cursor: pointer;
}
.video-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.video-btn:not(:disabled):hover { background: #5a52e0; }
.restart-btn {
  padding: 12px 20px;
  background: #fff;
  color: #555;
  border-radius: 10px;
  font-size: 14px;
  border: 2px solid #e0e0e0;
}
.restart-btn:hover { border-color: #6c63ff; color: #6c63ff; }
</style>
