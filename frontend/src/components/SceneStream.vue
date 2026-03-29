<template>
  <div class="scene-stream">
    <div v-for="ep in scenes" :key="ep.episode" class="episode-card">
      <div class="ep-header">
        <span class="ep-badge">第 {{ ep.episode }} 集</span>
        <span class="ep-title">{{ ep.title }}</span>
      </div>
      <div v-if="enableSceneKeyArt" class="scene-key-art-panel">
        <div class="scene-key-art-header">
          <div>
            <div class="scene-key-art-title">本集共享环境图组</div>
            <div class="scene-key-art-subtitle">同集相似场景共用一组图，每组只生成一张主场景参考图，差异大的场景会额外拆组</div>
          </div>
          <span class="scene-key-art-status" :class="assetStatusClass(getEpisodeStatus(ep.episode))">
            {{ assetStatusLabel(getEpisodeStatus(ep.episode)) }}
          </span>
        </div>
        <div v-if="getEpisodeGroups(ep.episode).length" class="scene-key-art-group-list">
          <div
            v-for="group in getEpisodeGroups(ep.episode)"
            :key="group.environment_pack_key"
            class="scene-key-art-group"
          >
            <div class="scene-key-art-group-top">
              <div>
                <div class="scene-key-art-group-title">{{ group.group_label || '环境组' }}</div>
                <div class="scene-key-art-group-copy">
                  覆盖场景：{{ formatSceneNumbers(group.affected_scene_numbers) }} · {{ group.summary_environment || '主环境' }}
                </div>
              </div>
            </div>
            <div class="scene-key-art-grid">
              <div
                class="scene-key-art-card"
                :class="{ ready: !!group.variants?.scene }"
              >
                <img
                  v-if="group.variants?.scene?.image_url"
                  :src="resolveAssetImageUrl(group.variants.scene.image_url)"
                  :alt="buildSceneReferenceAlt(group)"
                  class="scene-key-art-image"
                />
                <div v-else class="scene-key-art-placeholder">Scene Reference</div>
                <div class="scene-key-art-meta">
                  <span class="scene-key-art-label">主场景参考图</span>
                  <span class="scene-key-art-pill">scene</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="scene-key-art-empty">
          还没有生成环境组。点击下方按钮后，会按同集场景环境自动拆成 1 组或多组。
        </div>
        <div class="scene-key-art-actions">
          <button
            class="scene-key-art-btn"
            :disabled="getEpisodeStatus(ep.episode) === 'loading'"
            @click="$emit('generate-scene-key-art', { episode: ep.episode, scene: getEpisodeRepresentativeScene(ep) })"
          >
            {{ getEpisodeGroups(ep.episode).length ? '重新生成本集环境图组' : '生成本集环境图组' }}
          </button>
          <span v-if="getEpisodeError(ep.episode)" class="scene-key-art-error">
            {{ getEpisodeError(ep.episode) }}
          </span>
        </div>
      </div>
      <div class="scenes">
        <div v-for="scene in ep.scenes" :key="scene.scene_number" class="scene-block">
          <div class="scene-num">场景 {{ String(scene.scene_number).padStart(2, '0') }}</div>
          <div class="scene-row">
            <span class="scene-tag">【环境】</span>
            <span class="scene-text">{{ scene.environment }}</span>
          </div>
          <div class="scene-row">
            <span class="scene-tag">【画面】</span>
            <span class="scene-text">{{ scene.visual }}</span>
          </div>
          <div class="audio-block">
            <div v-for="(a, i) in scene.audio" :key="i" class="audio-line">
              <span class="character">{{ a.character }}</span>
              <span class="line">{{ a.line }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div v-if="streaming" class="streaming-indicator">
      <span class="dot"></span><span class="dot"></span><span class="dot"></span>
      正在生成...
    </div>
  </div>
</template>

<script setup>
import { useSettingsStore } from '../stores/settings.js'
import { getSceneKey } from '../stores/story.js'
import { resolveBackendMediaUrl } from '../utils/backend.js'

const props = defineProps({
  scenes: {
    type: Array,
    default: () => [],
  },
  streaming: Boolean,
  enableSceneKeyArt: Boolean,
  sceneReferenceAssets: {
    type: Object,
    default: () => ({}),
  },
})

defineEmits(['generate-scene-key-art'])

const settings = useSettingsStore()

function getSceneAsset(episode, sceneNumber) {
  return props.sceneReferenceAssets[getSceneKey(episode, sceneNumber)] || {
    status: 'idle',
    variants: {},
    error: '',
  }
}

function getEpisodeRepresentativeScene(episode) {
  return episode?.scenes?.[0] || { scene_number: 1 }
}

function getEpisodeAsset(episodeNumber) {
  const episode = props.scenes.find(item => item.episode === episodeNumber)
  const representativeScene = getEpisodeRepresentativeScene(episode)
  return getSceneAsset(episodeNumber, representativeScene.scene_number)
}

function getEpisodeGroups(episodeNumber) {
  const episode = props.scenes.find(item => item.episode === episodeNumber)
  const sceneKeys = (episode?.scenes || []).map(scene => getSceneKey(episodeNumber, scene.scene_number))
  const groups = []
  const seen = new Set()
  sceneKeys.forEach(sceneKey => {
    const asset = props.sceneReferenceAssets[sceneKey]
    const packKey = asset?.environment_pack_key
    if (!asset || !packKey || seen.has(packKey)) return
    seen.add(packKey)
    groups.push(asset)
  })
  return groups.sort((left, right) => (left.group_index || 0) - (right.group_index || 0))
}

function getEpisodeStatus(episodeNumber) {
  const groups = getEpisodeGroups(episodeNumber)
  if (groups.some(group => group.status === 'loading')) return 'loading'
  if (groups.some(group => group.status === 'failed')) return 'failed'
  if (groups.some(group => group.status === 'stale')) return 'stale'
  if (groups.some(group => group.status === 'idle')) return 'idle'
  if (groups.length > 0 && groups.every(group => group.status === 'ready')) return 'ready'
  return getEpisodeAsset(episodeNumber).status || 'idle'
}

function getEpisodeError(episodeNumber) {
  const groups = getEpisodeGroups(episodeNumber)
  return groups.find(group => group.error)?.error || getEpisodeAsset(episodeNumber).error || ''
}

function buildSceneReferenceAlt(group = {}) {
  const label = group.group_name || group.group_label || group.variants?.scene?.name || group.summary_environment || '环境组'
  return `${label} 主场景参考图`
}

function formatSceneNumbers(numbers = []) {
  return numbers.length ? numbers.map(number => String(number).padStart(2, '0')).join(' / ') : '--'
}

function assetStatusLabel(status) {
  return {
    idle: '未生成',
    loading: '生成中',
    ready: '已就绪',
    failed: '失败',
    stale: '需刷新',
  }[status] || '未生成'
}

function assetStatusClass(status) {
  return status || 'idle'
}

function resolveAssetImageUrl(url) {
  return resolveBackendMediaUrl(url, settings.backendUrl)
}
</script>

<style scoped>
.scene-stream { display: flex; flex-direction: column; gap: 16px; }
.episode-card {
  background: #fff;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  animation: fadeIn 0.4s ease;
}
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
.ep-header {
  background: #6c63ff;
  color: #fff;
  padding: 10px 16px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.ep-badge {
  background: rgba(255,255,255,0.2);
  padding: 2px 10px;
  border-radius: 20px;
  font-size: 12px;
}
.ep-title { font-weight: 600; font-size: 15px; }
.scenes { padding: 0 16px 14px; display: flex; flex-direction: column; gap: 20px; }
.scene-block {
  border-left: 3px solid #e0e0e0;
  padding-left: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.scene-num { font-size: 11px; font-weight: 700; color: #aaa; letter-spacing: 1px; margin-bottom: 2px; }
.scene-row { display: flex; gap: 6px; font-size: 13px; line-height: 1.6; }
.scene-tag { color: #6c63ff; font-weight: 700; white-space: nowrap; font-size: 12px; padding-top: 1px; }
.scene-text { color: #444; }
.audio-block {
  margin-top: 6px;
  background: #f8f7ff;
  border-radius: 8px;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.audio-line { display: flex; gap: 8px; font-size: 13px; }
.character { color: #6c63ff; font-weight: 600; white-space: nowrap; }
.line { color: #333; line-height: 1.5; }
.scene-key-art-panel {
  margin: 14px 16px;
  border-radius: 12px;
  border: 1px solid #ece8ff;
  background: linear-gradient(180deg, #fcfbff 0%, #f7f4ff 100%);
  padding: 12px;
}
.scene-key-art-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 10px;
}
.scene-key-art-title {
  color: #2f2a44;
  font-weight: 700;
  font-size: 13px;
}
.scene-key-art-subtitle {
  color: #7b7694;
  font-size: 12px;
  margin-top: 3px;
}
.scene-key-art-status {
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}
.scene-key-art-status.idle {
  background: #f2efff;
  color: #7a66d6;
}
.scene-key-art-status.loading {
  background: #fff6de;
  color: #9a6d00;
}
.scene-key-art-status.ready {
  background: #e8f8ec;
  color: #22804c;
}
.scene-key-art-status.failed {
  background: #ffe7e7;
  color: #ba3c3c;
}
.scene-key-art-status.stale {
  background: #eef0ff;
  color: #4f5fc4;
}
.scene-key-art-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.scene-key-art-group-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.scene-key-art-group {
  border-radius: 12px;
  border: 1px solid #e6dfff;
  background: rgba(255,255,255,0.75);
  padding: 10px;
}
.scene-key-art-group-top {
  margin-bottom: 10px;
}
.scene-key-art-group-title {
  color: #2f2a44;
  font-size: 13px;
  font-weight: 700;
}
.scene-key-art-group-copy {
  color: #756e92;
  font-size: 12px;
  margin-top: 3px;
}
.scene-key-art-empty {
  color: #7b7694;
  font-size: 12px;
  line-height: 1.6;
}
.scene-key-art-card {
  background: #fff;
  border: 1px solid #e3dcff;
  border-radius: 12px;
  overflow: hidden;
}
.scene-key-art-card.ready {
  box-shadow: 0 6px 14px rgba(108, 99, 255, 0.08);
}
.scene-key-art-image,
.scene-key-art-placeholder {
  width: 100%;
  aspect-ratio: 16 / 9;
  display: block;
}
.scene-key-art-image {
  object-fit: cover;
}
.scene-key-art-placeholder {
  display: grid;
  place-items: center;
  color: #998fc8;
  background:
    radial-gradient(circle at top left, rgba(108, 99, 255, 0.16), transparent 40%),
    linear-gradient(135deg, #f5f0ff 0%, #fbf9ff 100%);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.scene-key-art-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 8px 10px 10px;
}
.scene-key-art-label {
  color: #433d62;
  font-size: 12px;
  font-weight: 700;
}
.scene-key-art-pill {
  color: #8e84c4;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.scene-key-art-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}
.scene-key-art-btn {
  border: none;
  border-radius: 10px;
  padding: 9px 14px;
  background: #6c63ff;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}
.scene-key-art-btn:disabled {
  cursor: wait;
  opacity: 0.7;
}
.scene-key-art-error {
  color: #ba3c3c;
  font-size: 12px;
}
.streaming-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #999;
  font-size: 14px;
  padding: 8px 0;
}
.dot { width: 6px; height: 6px; background: #6c63ff; border-radius: 50%; animation: bounce 1s infinite; }
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
  40% { transform: scale(1.2); opacity: 1; }
}

@media (max-width: 720px) {
  .scene-key-art-grid {
    grid-template-columns: 1fr;
  }
  .scene-key-art-header,
  .scene-key-art-actions {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
