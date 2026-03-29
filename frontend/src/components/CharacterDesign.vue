<template>
  <div class="character-design-section">
    <div class="section-header">
      <h3>角色人设图</h3>
      <button class="generate-all-btn" @click="generateAll" :disabled="anyLoading">
        {{ isGenerating ? '生成中...' : '生成全部' }}
      </button>
    </div>

    <div class="carousel-container">
      <button class="nav-btn prev" @click="prev" :disabled="currentIndex === 0">
        ‹
      </button>

      <div class="carousel-viewport">
        <div class="carousel-track" :style="{ transform: `translateX(-${currentIndex * 100}%)` }">
          <div
            v-for="char in characters"
            :key="char.id || char.name"
            class="character-slide"
          >
            <div class="slide-content">
              <div class="card-image-area">
                <!-- 角色信息覆盖在图片上 -->
                <div class="image-overlay-header">
                  <span class="char-name">{{ char.name }}</span>
                  <span class="char-role">{{ char.role }}</span>
                </div>

                <div v-if="!getCharacterData(char).imageUrl" class="placeholder-image">
                  <span>待生成</span>
                </div>
                <img
                  v-else
                  :src="getMediaUrl(getCharacterData(char).imageUrl)"
                  :alt="char.name"
                  class="character-image"
                  @click="openPreview(char)"
                />

                <!-- 底部操作栏覆盖在图片上 -->
                <div class="image-overlay-footer">
                  <button
                    class="generate-btn"
                    @click="generateOne(char)"
                    :disabled="anyLoading"
                  >
                    {{ getCharacterData(char).loading ? '生成中...' : (getCharacterData(char).imageUrl ? '重新生成' : '生成人设') }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button class="nav-btn next" @click="next" :disabled="currentIndex >= characters.length - 1">
        ›
      </button>

      <div class="carousel-indicators">
        <span
          v-for="(_, i) in characters"
          :key="i"
          class="indicator"
          :class="{ active: i === currentIndex }"
          @click="goTo(i)"
        ></span>
      </div>
    </div>
  </div>

  <div v-if="error" class="error-tip">{{ error }}</div>

  <div
    v-if="previewImageUrl"
    class="image-preview-modal"
    @click.self="closePreview"
  >
    <div class="image-preview-dialog">
      <button type="button" class="image-preview-close" @click="closePreview">×</button>
      <img :src="previewImageUrl" :alt="previewCharacterName || '角色人设图预览'" class="image-preview-full" />
    </div>
  </div>

  <ApiKeyModal
    :show="showKeyModal"
    :type="keyModalType"
    :title="keyModalType === 'invalid' ? 'API Key 无效' : 'API Key 未设置'"
    :message="keyModalMsg"
    @close="showKeyModal = false"
  />
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useStoryStore } from '../stores/story.js'
import { useSettingsStore } from '../stores/settings.js'
import { generateCharacterImage, generateAllCharacterImages, getCharacterImages } from '../api/story.js'
import ApiKeyModal from './ApiKeyModal.vue'
import { resolveBackendMediaUrl } from '../utils/backend.js'
import { findCharacterByRef, findCharacterImageEntry, getCharacterKey } from '../utils/character.js'

const props = defineProps({
  characters: {
    type: Array,
    default: () => []
  }
})

const store = useStoryStore()
const settings = useSettingsStore()

function getMediaUrl(path) {
  return resolveBackendMediaUrl(path, settings.backendUrl)
}

const currentIndex = ref(0)
const isGenerating = ref(false)
const characterData = reactive({})
const error = ref('')
const showKeyModal = ref(false)
const keyModalType = ref('missing')
const keyModalMsg = ref('')
const previewImageUrl = ref('')
const previewCharacterName = ref('')

function isAuthError(msg) {
  return /401|403|invalid|incorrect|unauthorized|api.?key/i.test(msg)
}

function handleError(msg) {
  if (isAuthError(msg)) {
    keyModalType.value = 'invalid'
    keyModalMsg.value = 'API Key 无效或已过期，请检查后重新设置。'
    showKeyModal.value = true
  } else {
    error.value = msg || '生成失败，请重试'
  }
}

const anyLoading = computed(() =>
  isGenerating.value || Object.values(characterData).some(d => d.loading)
)

function getCharacterData(character) {
  const key = typeof character === 'string' ? character : getCharacterKey(character)
  if (!key) return { imageUrl: null, loading: false }
  if (!characterData[key]) {
    characterData[key] = { imageUrl: null, loading: false }
  }
  return characterData[key]
}

function resetCharacterData() {
  for (const key of Object.keys(characterData)) {
    delete characterData[key]
  }
  currentIndex.value = 0
}

function prev() {
  if (currentIndex.value > 0) {
    currentIndex.value--
  }
}

function next() {
  if (currentIndex.value < props.characters.length - 1) {
    currentIndex.value++
  }
}

function goTo(index) {
  currentIndex.value = index
}

function openPreview(char) {
  const imageUrl = getCharacterData(char).imageUrl
  if (!imageUrl) return
  previewImageUrl.value = getMediaUrl(imageUrl)
  previewCharacterName.value = char?.name || ''
}

function closePreview() {
  previewImageUrl.value = ''
  previewCharacterName.value = ''
}

function handleKeydown(event) {
  if (event.key === 'Escape' && previewImageUrl.value) {
    closePreview()
  }
}

async function generateOne(char) {
  if (!char || !store.storyId) return
  if (!char.id) {
    error.value = `角色「${char.name || '未命名'}」缺少 ID，已阻止按名字复用人设图`
    return
  }

  const key = getCharacterKey(char)
  const data = getCharacterData(key)
  data.loading = true

  try {
    const result = await generateCharacterImage(store.storyId, char)
    data.imageUrl = result.image_url
    store.characterImages = {
      ...(store.characterImages || {}),
      [result.character_id || key]: {
        ...(store.characterImages?.[result.character_id || key] || {}),
        image_url: result.image_url,
        prompt: result.prompt,
        character_id: result.character_id || char.id || '',
        character_name: char.name,
      },
    }
    error.value = ''
  } catch (e) {
    console.error('Failed to generate character image:', e)
    handleError(e.message)
  } finally {
    data.loading = false
  }
}

async function generateAll() {
  if (!store.storyId || props.characters.length === 0) return

  isGenerating.value = true

  for (const char of props.characters) {
    getCharacterData(char).loading = true
  }

  try {
    const { results, errors } = await generateAllCharacterImages(store.storyId, props.characters)
    const nextCharacterImages = { ...(store.characterImages || {}) }
    for (const result of results) {
      const char = findCharacterByRef(props.characters, {
        id: result.character_id,
      })
      const key = result.character_id || getCharacterKey(char)
      if (!key) continue
      const data = getCharacterData(key)
      data.imageUrl = result.image_url
      data.loading = false
      nextCharacterImages[key] = {
        ...(nextCharacterImages[key] || {}),
        image_url: result.image_url,
        prompt: result.prompt,
        character_id: result.character_id || char?.id || '',
        character_name: char?.name || result.character_name,
      }
    }
    store.characterImages = nextCharacterImages
    if (errors && errors.length > 0) {
      const names = errors.map(e => e.character_name).join('、')
      error.value = `以下角色生成失败: ${names}`
    } else {
      error.value = ''
    }
  } catch (e) {
    console.error('Failed to generate all character images:', e)
    handleError(e.message)
  } finally {
    isGenerating.value = false
    for (const char of props.characters) {
      getCharacterData(char).loading = false
    }
  }
}

async function loadExistingImages() {
  if (!store.storyId) return

  try {
    const { character_images } = await getCharacterImages(store.storyId)
    if (character_images) {
      store.characterImages = character_images
      for (const char of props.characters) {
        const data = findCharacterImageEntry(character_images, char)
        if (data?.image_url) {
          getCharacterData(char).imageUrl = data.image_url
        }
      }
      return
    }
  } catch (e) {
    console.log('No existing character images')
  }

  if (store.characterImages && Object.keys(store.characterImages).length > 0) {
    for (const char of props.characters) {
      const data = findCharacterImageEntry(store.characterImages, char)
      if (data?.image_url) {
        getCharacterData(char).imageUrl = data.image_url
      }
    }
  }
}

// Reset local state when story changes
watch(() => store.storyId, (newId, oldId) => {
  if (newId !== oldId) {
    resetCharacterData()
    closePreview()
    loadExistingImages()
  }
})

watch(() => props.characters.map(char => `${char.id || ''}:${char.name}`), () => {
  resetCharacterData()
  closePreview()
  loadExistingImages()
})

onMounted(loadExistingImages)
onMounted(() => document.addEventListener('keydown', handleKeydown))
onUnmounted(() => document.removeEventListener('keydown', handleKeydown))
</script>

<style scoped>
.character-design-section {
  margin-top: 20px;
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  border: 1px solid #e8e8e8;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.generate-all-btn {
  padding: 6px 12px;
  background: #6c63ff;
  color: #fff;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s;
}

.generate-all-btn:hover:not(:disabled) { opacity: 0.9; }
.generate-all-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.carousel-container {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  padding-bottom: 24px;
}

.carousel-viewport {
  flex: 1;
  overflow: hidden;
  border-radius: 12px;
}

.carousel-track {
  display: flex;
  transition: transform 0.3s ease;
}

.character-slide {
  flex: 0 0 100%;
  min-width: 0;
}

.slide-content {
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  overflow: hidden;
}

.card-image-area {
  position: relative;
  width: 100%;
  aspect-ratio: 3/4.8;
  border-radius: 12px;
  overflow: hidden;
  background: linear-gradient(135deg, #f0f0f0 0%, #e8e8e8 100%);
}

.image-overlay-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: 10px 12px;
  background: linear-gradient(to bottom, rgba(0,0,0,0.6) 0%, transparent 100%);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  z-index: 2;
}

.char-name {
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  text-shadow: 0 1px 3px rgba(0,0,0,0.3);
}

.char-role {
  font-size: 11px;
  color: #fff;
  background: rgba(108, 99, 255, 0.85);
  padding: 4px 10px;
  border-radius: 12px;
  font-weight: 500;
}

.placeholder-image {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #bbb;
  font-size: 14px;
  background: linear-gradient(135deg, #f5f5f5 0%, #ebebeb 100%);
}

.character-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  object-position: center;
  padding: 38px 2px 60px;
  cursor: zoom-in;
}

.image-overlay-footer {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 14px 12px 12px;
  background: linear-gradient(to top, rgba(0,0,0,0.7) 0%, transparent 100%);
  z-index: 2;
}

.generate-btn {
  width: 100%;
  padding: 10px;
  background: rgba(255,255,255,0.95);
  color: #6c63ff;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}

.generate-btn:hover:not(:disabled) {
  background: #fff;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}

.generate-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.nav-btn {
  width: 20px;
  height: 40px;
  background: transparent;
  color: #7a7a86;
  font-size: 18px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.nav-btn:hover:not(:disabled) {
  color: #6c63ff;
}

.nav-btn:disabled {
  opacity: 0.18;
  cursor: not-allowed;
}

.carousel-indicators {
  position: absolute;
  bottom: 4px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 8px;
}

.indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ddd;
  cursor: pointer;
  transition: all 0.2s;
}

.indicator.active {
  background: #6c63ff;
  width: 20px;
  border-radius: 4px;
}

.indicator:hover:not(.active) {
  background: #bbb;
}

.error-tip {
  margin-top: 10px;
  color: #e53935;
  font-size: 13px;
  text-align: center;
}

.image-preview-modal {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(12, 12, 18, 0.72);
  backdrop-filter: blur(4px);
}

.image-preview-dialog {
  position: relative;
  width: min(1100px, 100%);
  max-height: calc(100vh - 48px);
  padding: 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
}

.image-preview-close {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.08);
  color: #444;
  font-size: 28px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.image-preview-close:hover {
  background: rgba(0, 0, 0, 0.14);
}

.image-preview-full {
  display: block;
  width: 100%;
  max-height: calc(100vh - 84px);
  object-fit: contain;
  object-position: center;
  border-radius: 10px;
}

@media (max-width: 768px) {
  .card-image-area {
    aspect-ratio: 3/4.6;
  }

  .character-image {
    padding: 36px 2px 56px;
  }

  .image-preview-modal {
    padding: 12px;
  }

  .image-preview-dialog {
    padding: 14px;
    max-height: calc(100vh - 24px);
  }

  .image-preview-full {
    max-height: calc(100vh - 56px);
  }
}
</style>
