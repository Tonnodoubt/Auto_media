<template>
  <div class="art-style-selector">
    <button class="collapse-header" @click="expanded = !expanded">
      <span class="header-left">
        <span class="icon">🎨</span>
        <span class="label">视觉风格</span>
        <span class="style-badge" :class="{ empty: !store.artStyle }">{{ headerBadgeText }}</span>
      </span>
      <span class="chevron" :class="{ open: expanded }">›</span>
    </button>

    <div v-if="expanded" class="collapse-body">
      <p class="style-note">会影响角色图、场景图和视频画面风格，不影响剧情内容。</p>

      <div class="chips-row">
        <button
          v-for="preset in PRESETS"
          :key="preset.id"
          class="chip"
          :class="{ active: selectedPresetId === preset.id }"
          @click="selectPreset(preset)"
        >{{ preset.icon }} {{ preset.name }}</button>
      </div>

      <div class="input-row">
        <textarea
          v-model="localStyle"
          class="style-input"
          rows="3"
          placeholder="先写你想要的画面感觉，例如：像韩剧，高级感一点，冷白色调，夜景霓虹不要太夸张"
          @input="onTextInput"
        />
      </div>

      <div class="assist-row">
        <button
          class="assist-btn"
          :disabled="!canPolishStyle"
          @click="handlePolishStyle"
        >{{ polishing ? '整理中…' : 'AI 帮我整理风格描述' }}</button>
        <button
          v-if="showResetButton"
          class="clear-btn"
          @click="restoreDefaultStyle"
        >恢复默认</button>
      </div>

      <div v-if="polishHint" class="polish-hint">{{ polishHint }}</div>
      <div v-if="polishError" class="error-hint">{{ polishError }}</div>

      <div class="confirm-row">
        <span v-if="saved" class="saved-hint">✓ 已保存</span>
        <span v-if="saveError" class="error-hint">{{ saveError }}</span>
        <button
          class="confirm-btn"
          :disabled="confirmDisabled"
          @click="confirmStyle"
        >确认</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useStoryStore } from '../stores/story.js'
import { patchStory, polishVisualStyle } from '../api/story.js'
import { ART_STYLE_PRESETS, ART_STYLE_PROMPT_TO_LABEL, ART_STYLE_TRUNCATE_LEN, DEFAULT_ART_STYLE_PRESET, DEFAULT_ART_STYLE_PROMPT } from '../constants/artStylePresets.js'

const store = useStoryStore()
const PRESETS = ART_STYLE_PRESETS

const expanded = ref(false)
const selectedPresetId = ref(null)
const localStyle = ref('')
const saved = ref(false)
const saveError = ref('')
const polishing = ref(false)
const polishHint = ref('')
const polishError = ref('')

const normalizedLocalStyle = computed(() => String(localStyle.value || '').trim())
const confirmedEffectiveStyle = computed(() => String(store.artStyle || DEFAULT_ART_STYLE_PROMPT).trim())
const localEffectiveStyle = computed(() => normalizedLocalStyle.value || DEFAULT_ART_STYLE_PROMPT)
const confirmDisabled = computed(() => localEffectiveStyle.value === confirmedEffectiveStyle.value)
const canPolishStyle = computed(() => Boolean(normalizedLocalStyle.value) && !polishing.value)
const showResetButton = computed(() => localEffectiveStyle.value !== DEFAULT_ART_STYLE_PROMPT)

const confirmedPresetName = computed(() => {
  return ART_STYLE_PROMPT_TO_LABEL.get(confirmedEffectiveStyle.value) || null
})

const headerBadgeText = computed(() => {
  if (!String(store.artStyle || '').trim()) {
    return `${DEFAULT_ART_STYLE_PRESET?.name || '写实摄影'}（默认）`
  }
  if (confirmedPresetName.value) {
    return confirmedPresetName.value
  }
  return confirmedEffectiveStyle.value.length > ART_STYLE_TRUNCATE_LEN
    ? `${confirmedEffectiveStyle.value.slice(0, ART_STYLE_TRUNCATE_LEN)}...`
    : confirmedEffectiveStyle.value
})

onMounted(() => {
  localStyle.value = store.artStyle || DEFAULT_ART_STYLE_PROMPT
  const match = PRESETS.find(p => p.prompt === localStyle.value)
  selectedPresetId.value = match ? match.id : DEFAULT_ART_STYLE_PRESET?.id || null
})

function resetTransientState() {
  saved.value = false
  saveError.value = ''
  polishHint.value = ''
  polishError.value = ''
}

function selectPreset(preset) {
  resetTransientState()
  if (selectedPresetId.value === preset.id) {
    selectedPresetId.value = DEFAULT_ART_STYLE_PRESET?.id || null
    localStyle.value = DEFAULT_ART_STYLE_PROMPT
  } else {
    selectedPresetId.value = preset.id
    localStyle.value = preset.prompt
  }
}

function onTextInput() {
  resetTransientState()
  const match = PRESETS.find(p => p.prompt === localStyle.value)
  selectedPresetId.value = match ? match.id : null
}

function restoreDefaultStyle() {
  resetTransientState()
  localStyle.value = DEFAULT_ART_STYLE_PROMPT
  selectedPresetId.value = DEFAULT_ART_STYLE_PRESET?.id || null
}

async function handlePolishStyle() {
  const description = normalizedLocalStyle.value
  const confirmedStyleAtRequest = String(store.artStyle || '').trim()
  if (!description || polishing.value) return

  resetTransientState()
  polishing.value = true
  try {
    const result = await polishVisualStyle(description, confirmedStyleAtRequest)
    const polished = String(result?.polished_style || '').trim()
    if (!polished) {
      throw new Error('整理结果为空，请重试')
    }
    if (
      normalizedLocalStyle.value !== description
      || String(store.artStyle || '').trim() !== confirmedStyleAtRequest
    ) {
      polishHint.value = '整理结果已返回，但你期间已经更新了风格输入，当前保留的是你的最新编辑。'
      return
    }
    localStyle.value = polished
    onTextInput()
    polishHint.value = '已整理为更稳定的视觉风格描述，确认后才会生效。'
  } catch (error) {
    console.error('Failed to polish visual style:', error)
    polishError.value = error?.message || '整理失败，请重试'
  } finally {
    polishing.value = false
  }
}

async function confirmStyle() {
  const previousState = {
    localStyle: localStyle.value,
    selectedPresetId: selectedPresetId.value,
    artStyle: store.artStyle,
    saved: saved.value,
    expanded: expanded.value,
  }

  resetTransientState()
  const nextStyle = normalizedLocalStyle.value
  store.setArtStyle(nextStyle)
  localStyle.value = nextStyle || DEFAULT_ART_STYLE_PROMPT
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

<style scoped src="../style/components/artstyleselector.css"></style>
