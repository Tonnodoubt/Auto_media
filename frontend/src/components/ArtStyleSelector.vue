<template>
  <div class="art-style-selector">
    <!-- 折叠头 -->
    <button class="collapse-header" @click="expanded = !expanded">
      <span class="header-left">
        <span class="icon">🎨</span>
        <span class="label">画风设定</span>
        <span class="style-badge" :class="{ empty: !store.artStyle }">{{ confirmedPresetName || '写实摄影（默认）' }}</span>
      </span>
      <span class="chevron" :class="{ open: expanded }">›</span>
    </button>

    <!-- 展开内容 -->
    <div v-if="expanded" class="collapse-body">
      <!-- 预设 chips -->
      <div class="chips-row">
        <button
          v-for="preset in PRESETS"
          :key="preset.id"
          class="chip"
          :class="{ active: selectedPresetId === preset.id }"
          @click="selectPreset(preset)"
        >{{ preset.icon }} {{ preset.name }}</button>
      </div>
      <!-- 输入框 -->
      <div class="input-row">
        <input
          v-model="localStyle"
          class="style-input"
          placeholder="或直接输入画风描述…"
          @input="onTextInput"
        />
        <button v-if="localStyle" class="clear-btn" @click="clearStyle">✕</button>
      </div>
      <!-- 确认行 -->
      <div class="confirm-row">
        <span v-if="saved" class="saved-hint">✓ 已保存</span>
        <span v-if="saveError" class="error-hint">{{ saveError }}</span>
        <button
          class="confirm-btn"
          :disabled="localStyle === (store.artStyle || DEFAULT_ART_STYLE_PROMPT)"
          @click="confirmStyle"
        >确认</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useStoryStore } from '../stores/story.js'
import { patchStory } from '../api/story.js'
import { ART_STYLE_PRESETS, DEFAULT_ART_STYLE_PRESET, DEFAULT_ART_STYLE_PROMPT } from '../constants/artStylePresets.js'

const store = useStoryStore()
const PRESETS = ART_STYLE_PRESETS

const expanded = ref(false)
const selectedPresetId = ref(null)
const localStyle = ref('')
const saved = ref(false)
const saveError = ref('')

/** 已确认保存的 preset 名（根据 store 中的值） */
const confirmedPresetName = computed(() => {
  const foundPreset = PRESETS.find(preset => preset.prompt === (store.artStyle || DEFAULT_ART_STYLE_PROMPT))
  return foundPreset ? foundPreset.name : null
})

onMounted(() => {
  localStyle.value = store.artStyle || DEFAULT_ART_STYLE_PROMPT
  const match = PRESETS.find(p => p.prompt === localStyle.value)
  selectedPresetId.value = match ? match.id : DEFAULT_ART_STYLE_PRESET?.id || null
})

/** 点击预设：只更新本地状态，不写入 store */
function selectPreset(preset) {
  if (selectedPresetId.value === preset.id) {
    selectedPresetId.value = DEFAULT_ART_STYLE_PRESET?.id || null
    localStyle.value = DEFAULT_ART_STYLE_PROMPT
  } else {
    selectedPresetId.value = preset.id
    localStyle.value = preset.prompt
  }
}

/** 输入框输入：只更新本地状态 */
function onTextInput() {
  const match = PRESETS.find(p => p.prompt === localStyle.value)
  selectedPresetId.value = match ? match.id : null
}

/** 清除：立即清空并持久化 */
async function clearStyle() {
  const previousState = {
    localStyle: localStyle.value,
    selectedPresetId: selectedPresetId.value,
    artStyle: store.artStyle,
    saved: saved.value,
    expanded: expanded.value,
  }
  saveError.value = ''
  localStyle.value = DEFAULT_ART_STYLE_PROMPT
  selectedPresetId.value = DEFAULT_ART_STYLE_PRESET?.id || null
  store.setArtStyle('')
  if (store.storyId) {
    try {
      const result = await patchStory(store.storyId, { art_style: '' })
      if (!result) throw new Error('patchStory returned no result')
    } catch (error) {
      console.error('Failed to clear art style:', error)
      localStyle.value = previousState.localStyle
      selectedPresetId.value = previousState.selectedPresetId
      store.setArtStyle(previousState.artStyle)
      saved.value = previousState.saved
      expanded.value = previousState.expanded
      saveError.value = '清除失败，请重试'
    }
  }
}

/** 确认：写入 store（localStorage）并持久化到后端 */
async function confirmStyle() {
  const previousState = {
    localStyle: localStyle.value,
    selectedPresetId: selectedPresetId.value,
    artStyle: store.artStyle,
    saved: saved.value,
    expanded: expanded.value,
  }
  saveError.value = ''
  store.setArtStyle(localStyle.value)
  localStyle.value = store.artStyle
  const match = PRESETS.find(preset => preset.prompt === localStyle.value)
  selectedPresetId.value = match ? match.id : null
  try {
    if (store.storyId) {
      const result = await patchStory(store.storyId, { art_style: store.artStyle })
      if (!result) throw new Error('patchStory returned no result')
    }
  } catch (error) {
    console.error('Failed to persist art style:', error)
    localStyle.value = previousState.localStyle
    selectedPresetId.value = previousState.selectedPresetId
    store.setArtStyle(previousState.artStyle)
    saved.value = previousState.saved
    expanded.value = previousState.expanded
    saveError.value = '保存失败，请重试'
    return
  }
  saved.value = true
  setTimeout(() => { saved.value = false }, 2000)
  expanded.value = false
}

watch(() => store.artStyle, (val) => {
  const effectiveStyle = val || DEFAULT_ART_STYLE_PROMPT
  if (effectiveStyle !== localStyle.value) {
    localStyle.value = effectiveStyle
    const match = PRESETS.find(p => p.prompt === effectiveStyle)
    selectedPresetId.value = match ? match.id : DEFAULT_ART_STYLE_PRESET?.id || null
  }
})
</script>

<style scoped>
.art-style-selector {
  margin-top: 12px;
  background: #fff;
  border: 1.5px solid #e8e4ff;
  border-radius: 12px;
  overflow: hidden;
}

/* 折叠头 */
.collapse-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  color: #333;
}

.collapse-header:hover { background: #faf9ff; }

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.icon { font-size: 16px; }

.label { font-weight: 600; font-size: 13px; }

.style-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 20px;
  background: #ede9fe;
  color: #6c63ff;
  font-weight: 500;
}

.style-badge.empty {
  background: #f3f3f3;
  color: #aaa;
}

.chevron {
  font-size: 18px;
  color: #aaa;
  transition: transform 0.18s;
  line-height: 1;
}
.chevron.open { transform: rotate(90deg); }

/* 展开内容 */
.collapse-body {
  padding: 0 14px 12px;
  border-top: 1px solid #f0eeff;
}

/* 预设 chips */
.chips-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 0 8px;
}

.chip {
  padding: 4px 10px;
  border-radius: 20px;
  border: 1.5px solid #e0e0e0;
  background: #fafafa;
  font-size: 12px;
  color: #555;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.chip:hover { border-color: #c4b5fd; color: #6c63ff; background: #f3f0ff; }

.chip.active {
  border-color: #6c63ff;
  background: #ede9fe;
  color: #6c63ff;
  font-weight: 600;
}

/* 输入行 */
.input-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.style-input {
  flex: 1;
  padding: 7px 10px;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  font-size: 13px;
  color: #333;
  font-family: inherit;
  transition: border-color 0.2s;
}

.style-input:focus { border-color: #6c63ff; outline: none; }
.style-input::placeholder { color: #ccc; }

.clear-btn {
  padding: 6px 8px;
  font-size: 12px;
  color: #bbb;
  background: none;
  border: none;
  cursor: pointer;
  border-radius: 6px;
  transition: color 0.15s;
  flex-shrink: 0;
}
.clear-btn:hover { color: #e53935; }

/* 确认行 */
.confirm-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 8px;
}

.saved-hint {
  font-size: 12px;
  color: #22c55e;
}

.error-hint {
  font-size: 12px;
  color: #e53935;
}

.confirm-btn {
  padding: 6px 18px;
  border-radius: 8px;
  border: none;
  background: #6c63ff;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
}

.confirm-btn:hover:not(:disabled) { background: #5a52d5; }

.confirm-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
