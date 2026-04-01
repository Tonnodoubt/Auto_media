<template>
  <div class="step-wrapper">
    <div class="top-actions">
      <div class="usage-badge">
        <span class="usage-icon">⚡</span>
        <span class="usage-num">{{ store.totalTokens.toLocaleString() }}</span>
        <span class="usage-unit">tokens</span>
        <span class="usage-detail">↑{{ store.usage.prompt_tokens.toLocaleString() }} ↓{{ store.usage.completion_tokens.toLocaleString() }}</span>
      </div>
      <button v-if="current > 1" class="back-top-btn" @click="goBack" :disabled="loading">← 上一步</button>
      <button class="settings-btn" @click="router.push('/settings')" :disabled="loading">⚙ 设置</button>
    </div>
    <div class="step-indicator">
      <button
        v-for="step in steps"
        :key="step.id"
        type="button"
        class="step-item"
        :class="{
          active: current === step.id,
          done: current > step.id,
          clickable: !loading && current !== step.id && canGoStep(step),
        }"
        :aria-current="current === step.id ? 'step' : undefined"
        :disabled="loading || !canGoStep(step)"
        @click="goStep(step)"
      >
        <span class="step-dot">{{ current > step.id ? '✓' : step.id }}</span>
        <span class="step-text">
          <span class="step-kicker">Step {{ step.id }}</span>
          <span class="step-label">{{ step.label }}</span>
        </span>
      </button>
      <div class="step-line" :style="{ transform: lineTransform }"></div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useStoryStore } from '../stores/story.js'
import { canAccessStep } from '../utils/stepAccess.js'

const props = defineProps({ current: Number, loading: Boolean })
const steps = [
  { id: 1, label: '输入灵感', route: '/step1' },
  { id: 2, label: '选择设定', route: '/step2' },
  { id: 3, label: '生成剧本', route: '/step3' },
  { id: 4, label: '预览导出', route: '/step4' },
  { id: 5, label: '视频生成', route: '/video-generation' },
]
const lineTransform = computed(() => `scaleX(${Math.max(0, (props.current - 1) / (steps.length - 1))})`)

const router = useRouter()
const store = useStoryStore()

const prevRoutes = { 2: '/step1', 3: '/step2', 4: '/step3', 5: '/step4' }

function goBack() {
  store.setStep(props.current - 1)
  router.push(prevRoutes[props.current])
}

function goStep(step) {
  if (!step || props.loading || !canGoStep(step)) return
  store.setStep(step.id)
  router.push(step.route)
}

function canGoStep(step) {
  return canAccessStep(store, step?.id)
}
</script>

<style scoped src="../style/stepindicator.css"></style>
