<template>
  <div class="page">
    <div class="header">
      <button class="back-btn" @click="router.push('/step1')">← 返回</button>
      <h1>历史剧本</h1>
    </div>

    <div class="content">
      <div v-if="loading" class="empty">加载中...</div>

      <div v-else-if="error" class="empty error">{{ error }}</div>

      <div v-else-if="stories.length === 0" class="empty">
        暂无已保存的剧本，快去创作吧！
      </div>

      <div v-else class="list">
        <div
          v-for="story in stories"
          :key="story.id"
          class="story-card"
          @click="loadStory(story.id)"
        >
          <div class="story-main">
            <div class="story-idea">{{ story.idea || '（无标题）' }}</div>
            <div class="story-meta">
              <span v-if="story.genre" class="tag">{{ story.genre }}</span>
              <span v-if="story.tone" class="tag">{{ story.tone }}</span>
              <span v-if="story.has_script" class="tag green">含剧本</span>
              <span v-if="story.has_character_images" class="tag purple">含人设</span>
              <span
                v-if="story.art_style"
                class="tag art-style"
                :title="story.art_style"
              >
                画风: {{ formatArtStyleTag(story.art_style) }}
              </span>
            </div>
          </div>
          <div class="story-right">
            <div class="story-date">{{ formatDate(story.created_at) }}</div>
            <div class="story-actions">
              <button
                v-if="story.has_script"
                class="btn-storyboard"
                @click.stop="goStoryboard(story.id)"
              >
                直接分镜
              </button>
              <button class="btn-load" @click.stop="loadStory(story.id)">
                查看
              </button>
              <button class="btn-delete" @click.stop="confirmDelete(story)">
                删除
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="loadingStory" class="overlay">
      <div class="overlay-text">加载剧本中...</div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="deleteTarget" class="overlay" @click.self="deleteTarget = null">
      <div class="confirm-box">
        <div class="confirm-title">确认删除</div>
        <div class="confirm-msg">「{{ deleteTarget.idea || '（无标题）' }}」删除后无法恢复，确定吗？</div>
        <div class="confirm-actions">
          <button class="confirm-cancel" @click="deleteTarget = null">取消</button>
          <button class="confirm-ok" :disabled="deleting" @click="doDelete">
            {{ deleting ? '删除中...' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listStories, getStory, deleteStory } from '../api/story.js'
import { useStoryStore } from '../stores/story.js'
import { ART_STYLE_PROMPT_TO_LABEL, ART_STYLE_TRUNCATE_LEN } from '../constants/artStylePresets.js'
import { hasCompleteGeneratedScript } from '../utils/scriptValidation.js'

const router = useRouter()
const store = useStoryStore()

const stories = ref([])
const loading = ref(true)
const loadingStory = ref(false)
const error = ref(null)
const deleteTarget = ref(null)
const deleting = ref(false)

onMounted(async () => {
  try {
    stories.value = await listStories()
  } catch (e) {
    error.value = '加载失败：' + e.message
  } finally {
    loading.value = false
  }
})

function formatDate(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function formatArtStyleTag(artStyle) {
  const normalized = typeof artStyle === 'string' ? artStyle.trim() : ''
  if (!normalized) return ''
  if (ART_STYLE_PROMPT_TO_LABEL.has(normalized)) {
    return ART_STYLE_PROMPT_TO_LABEL.get(normalized)
  }
  return normalized.length > ART_STYLE_TRUNCATE_LEN
    ? `${normalized.slice(0, ART_STYLE_TRUNCATE_LEN)}...`
    : normalized
}

async function loadStory(storyId) {
  loadingStory.value = true
  try {
    const data = await getStory(storyId)
    store.loadStory(data)
    // 根据剧本完整度跳转到合适的步骤
    if (hasCompleteGeneratedScript({ outline: data.outline, scenes: data.scenes })) {
      router.push('/step4')
    } else if (data.characters && data.characters.length > 0) {
      router.push('/step3')
    } else if (data.selected_setting) {
      router.push('/step2')
    } else {
      router.push('/step2')
    }
  } catch (e) {
    alert('加载剧本失败：' + e.message)
  } finally {
    loadingStory.value = false
  }
}

async function goStoryboard(storyId) {
  loadingStory.value = true
  try {
    const data = await getStory(storyId)
    store.loadStory(data)
    router.push('/video-generation')
  } catch (e) {
    alert('加载剧本失败：' + e.message)
  } finally {
    loadingStory.value = false
  }
}

function confirmDelete(story) {
  deleteTarget.value = story
}

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await deleteStory(deleteTarget.value.id)
    stories.value = stories.value.filter(s => s.id !== deleteTarget.value.id)
    deleteTarget.value = null
  } catch (e) {
    alert('删除失败：' + e.message)
  } finally {
    deleting.value = false
  }
}
</script>

<style scoped src="../style/historyview.css"></style>
