<template>
  <div class="step-wrapper">
    <div class="step-indicator">
      <div
        v-for="(label, i) in steps"
        :key="i"
        class="step-item"
        :class="{ active: current === i + 1, done: current > i + 1 }"
      >
        <div class="step-dot">{{ current > i + 1 ? '✓' : i + 1 }}</div>
        <span class="step-label">{{ label }}</span>
      </div>
      <div class="step-line" :style="{ width: lineWidth }"></div>
    </div>
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
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useStoryStore } from '../stores/story.js'

const props = defineProps({ current: Number, loading: Boolean })
const steps = ['输入灵感', '选择设定', '生成剧本', '预览导出', '视图生成']
const lineWidth = `${((props.current - 1) / 4) * 100}%`

const router = useRouter()
const store = useStoryStore()

const prevRoutes = { 2: '/step1', 3: '/step2', 4: '/step3', 5: '/step4' }

function goBack() {
  store.setStep(props.current - 1)
  router.push(prevRoutes[props.current])
}
</script>

<style scoped>
.step-wrapper {
  position: relative;
  max-width: 900px;
  margin: 0 auto;
}
.step-indicator {
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: relative;
  padding: 0 16px;
  max-width: 600px;
  margin: 0 auto;
}
.top-actions {
  position: absolute;
  top: 0;
  right: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.usage-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  background: #fff;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  padding: 5px 10px;
  font-size: 12px;
  color: #555;
}
.usage-icon { font-size: 13px; }
.usage-num { font-weight: 700; color: #6c63ff; }
.usage-unit { color: #aaa; }
.usage-detail { color: #bbb; font-size: 11px; margin-left: 2px; }
.back-top-btn {
  padding: 6px 14px;
  background: #fff;
  color: #6c63ff;
  border: 1.5px solid #6c63ff;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}
.back-top-btn:hover { background: #f0eeff; }
.back-top-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.settings-btn {
  padding: 6px 14px;
  background: #fff;
  color: #888;
  border: 1.5px solid #e0e0e0;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}
.settings-btn:hover:not(:disabled) { border-color: #6c63ff; color: #6c63ff; background: #f0eeff; }
.settings-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.step-indicator::before {
  content: '';
  position: absolute;
  top: 18px;
  left: 40px;
  right: 40px;
  height: 2px;
  background: #e0e0e0;
  z-index: 0;
}
.step-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  z-index: 1;
}
.step-dot {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #e0e0e0;
  color: #999;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 14px;
  transition: all 0.3s;
}
.step-item.active .step-dot { background: #6c63ff; color: #fff; }
.step-item.done .step-dot { background: #4caf50; color: #fff; }
.step-label { font-size: 12px; color: #999; }
.step-item.active .step-label,
.step-item.done .step-label { color: #333; }
</style>
