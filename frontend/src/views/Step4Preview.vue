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
          <span>{{ readyEpisodeKeyArtCount }}/{{ store.scenes.length }} 集环境图组</span>
        </div>
      </div>

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

      <SceneStream
        :scenes="currentEpisodeScenes"
        :streaming="false"
        :enable-scene-key-art="true"
        :scene-reference-assets="store.sceneReferenceAssets"
        @generate-scene-key-art="handleGenerateSceneKeyArt"
      />

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
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import StepIndicator from '../components/StepIndicator.vue'
import SceneStream from '../components/SceneStream.vue'
import ExportPanel from '../components/ExportPanel.vue'
import { generateEpisodeSceneReference } from '../api/story.js'
import { useStoryStore } from '../stores/story.js'
import { canAccessStep, getStepRedirectPath } from '../utils/stepAccess.js'

const router = useRouter()
const store = useStoryStore()
const currentEpisodeIndex = ref(0)

onMounted(() => {
  if (!canAccessStep(store, 4)) {
    router.replace(getStepRedirectPath(store, 4))
    return
  }
  store.ensureSceneReferenceAssets()
})

const episodeCount = computed(() => store.scenes.length)
const currentEpisode = computed(() => store.scenes[currentEpisodeIndex.value] || null)
const currentEpisodeScenes = computed(() => (currentEpisode.value ? [currentEpisode.value] : []))
const canGoPrev = computed(() => currentEpisodeIndex.value > 0)
const canGoNext = computed(() => currentEpisodeIndex.value < episodeCount.value - 1)

const totalScenes = computed(() =>
  store.scenes.reduce((sum, s) => sum + s.scenes.length, 0)
)

const readyEpisodeKeyArtCount = computed(() =>
  store.scenes.filter(episode => store.getEpisodeSceneReferenceStatus(episode.episode) === 'ready').length
)

async function handleGenerateSceneKeyArt({ episode, scene }) {
  store.setEpisodeSceneReferenceStatus(episode, 'loading', '')
  try {
    const forceRegenerate = store.getEpisodeSceneReferenceGroups(episode).length > 0
    const result = await generateEpisodeSceneReference(store.storyId, episode, { forceRegenerate })
    store.applyEpisodeSceneReferenceAsset(result)
  } catch (error) {
    store.setEpisodeSceneReferenceStatus(episode, 'failed', error.message || '环境图生成失败')
  }
}

function generateVideo() {
  router.push('/video-generation')
}

function restart() {
  store.$reset()
  router.push('/step1')
}

function goPrevEpisode() {
  if (!canGoPrev.value) return
  currentEpisodeIndex.value -= 1
}

function goNextEpisode() {
  if (!canGoNext.value) return
  currentEpisodeIndex.value += 1
}
</script>

<style scoped src="../style/step4preview.css"></style>
