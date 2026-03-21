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
            :key="char.name"
            class="character-slide"
          >
            <div class="slide-content">
              <div class="card-image-area">
                <!-- 角色信息覆盖在图片上 -->
                <div class="image-overlay-header">
                  <span class="char-name">{{ char.name }}</span>
                  <span class="char-role">{{ char.role }}</span>
                </div>

                <div v-if="!getCharacterData(char.name).imageUrl" class="placeholder-image">
                  <span>待生成</span>
                </div>
                <img v-else :src="getCharacterData(char.name).imageUrl" :alt="char.name" class="character-image" />

                <!-- 底部操作栏覆盖在图片上 -->
                <div class="image-overlay-footer">
                  <button
                    class="generate-btn"
                    @click="generateOne(char.name)"
                    :disabled="anyLoading"
                  >
                    {{ getCharacterData(char.name).loading ? '生成中...' : (getCharacterData(char.name).imageUrl ? '重新生成' : '生成人设') }}
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
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useStoryStore } from '../stores/story.js'
import { generateCharacterImage, generateAllCharacterImages, getCharacterImages } from '../api/story.js'

const props = defineProps({
  characters: {
    type: Array,
    default: () => []
  }
})

const store = useStoryStore()
const currentIndex = ref(0)
const isGenerating = ref(false)
const characterData = reactive({})

const anyLoading = computed(() =>
  isGenerating.value || Object.values(characterData).some(d => d.loading)
)

function getCharacterData(name) {
  if (!characterData[name]) {
    characterData[name] = { imageUrl: null, loading: false }
  }
  return characterData[name]
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

async function generateOne(name) {
  const char = props.characters.find(c => c.name === name)
  if (!char || !store.storyId) return

  const data = getCharacterData(name)
  data.loading = true

  try {
    const result = await generateCharacterImage(store.storyId, char)
    data.imageUrl = result.image_url
  } catch (e) {
    console.error('Failed to generate character image:', e)
    alert(`生成失败: ${e.message}`)
  } finally {
    data.loading = false
  }
}

async function generateAll() {
  if (!store.storyId || props.characters.length === 0) return

  isGenerating.value = true

  for (const char of props.characters) {
    getCharacterData(char.name).loading = true
  }

  try {
    const { results, errors } = await generateAllCharacterImages(store.storyId, props.characters)
    for (const result of results) {
      const data = getCharacterData(result.character_name)
      data.imageUrl = result.image_url
      data.loading = false
    }
    if (errors && errors.length > 0) {
      const names = errors.map(e => e.character_name).join('、')
      alert(`以下角色生成失败: ${names}`)
    }
  } catch (e) {
    console.error('Failed to generate all character images:', e)
    alert(`批量生成失败: ${e.message}`)
  } finally {
    isGenerating.value = false
    for (const char of props.characters) {
      getCharacterData(char.name).loading = false
    }
  }
}

async function loadExistingImages() {
  if (!store.storyId) return
  try {
    const { character_images } = await getCharacterImages(store.storyId)
    if (character_images) {
      for (const [name, data] of Object.entries(character_images)) {
        getCharacterData(name).imageUrl = data.image_url
      }
    }
  } catch (e) {
    console.log('No existing character images')
  }
}

// Reset local state when story changes
watch(() => store.storyId, (newId, oldId) => {
  if (newId !== oldId) {
    resetCharacterData()
    loadExistingImages()
  }
})

onMounted(loadExistingImages)
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
  gap: 12px;
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
  aspect-ratio: 3/4;
  border-radius: 12px;
  overflow: hidden;
  background: linear-gradient(135deg, #f0f0f0 0%, #e8e8e8 100%);
}

.image-overlay-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: 14px 16px;
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
  object-fit: cover;
}

.image-overlay-footer {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 20px 16px 16px;
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
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #fff;
  color: #666;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid #e8e8e8;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.nav-btn:hover:not(:disabled) {
  background: #6c63ff;
  color: #fff;
}

.nav-btn:disabled {
  opacity: 0.3;
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
</style>
