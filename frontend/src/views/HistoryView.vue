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

async function loadStory(storyId) {
  loadingStory.value = true
  try {
    const data = await getStory(storyId)
    store.loadStory(data)
    // 根据剧本完整度跳转到合适的步骤
    if (data.scenes && data.scenes.length > 0) {
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

<style scoped>
.page {
  min-height: 100vh;
  background: #f5f5f7;
  padding: 24px 16px;
}

.header {
  display: flex;
  align-items: center;
  gap: 16px;
  max-width: 700px;
  margin: 0 auto 24px;
}

.back-btn {
  background: none;
  border: none;
  color: #6c63ff;
  font-size: 15px;
  cursor: pointer;
  padding: 0;
}

h1 {
  font-size: 22px;
  font-weight: 700;
  margin: 0;
}

.content {
  max-width: 700px;
  margin: 0 auto;
}

.empty {
  text-align: center;
  color: #999;
  padding: 60px 0;
  font-size: 15px;
}

.empty.error { color: #e53e3e; }

.list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.story-card {
  background: #fff;
  border-radius: 14px;
  padding: 16px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  transition: box-shadow 0.15s;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.story-card:hover {
  box-shadow: 0 4px 16px rgba(108,99,255,0.12);
}

.story-main {
  flex: 1;
  min-width: 0;
}

.story-idea {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 8px;
}

.story-meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.tag {
  background: #f0eeff;
  color: #6c63ff;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 20px;
}

.tag.green {
  background: #e6f7ef;
  color: #38a169;
}

.story-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
  margin-left: 16px;
  flex-shrink: 0;
}

.story-date {
  font-size: 12px;
  color: #aaa;
  white-space: nowrap;
}

.story-actions {
  display: flex;
  gap: 8px;
}

.btn-load {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1.5px solid #e0e0e0;
  background: #fff;
  color: #555;
  font-size: 13px;
  cursor: pointer;
}

.btn-load:hover { border-color: #6c63ff; color: #6c63ff; }

.btn-storyboard {
  padding: 6px 14px;
  border-radius: 8px;
  border: none;
  background: #6c63ff;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.btn-storyboard:hover { background: #5a52e0; }

.btn-delete {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1.5px solid #fecaca;
  background: #fff;
  color: #e53e3e;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.btn-delete:hover { background: #fff5f5; border-color: #e53e3e; }

.confirm-box {
  background: #fff;
  border-radius: 16px;
  padding: 28px 28px 20px;
  width: 320px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.15);
}

.confirm-title {
  font-size: 17px;
  font-weight: 700;
  margin-bottom: 10px;
  color: #1a1a2e;
}

.confirm-msg {
  font-size: 14px;
  color: #555;
  line-height: 1.6;
  margin-bottom: 20px;
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.confirm-cancel {
  padding: 8px 18px;
  border-radius: 8px;
  border: 1.5px solid #e0e0e0;
  background: #fff;
  color: #555;
  font-size: 14px;
  cursor: pointer;
}

.confirm-cancel:hover { border-color: #aaa; }

.confirm-ok {
  padding: 8px 18px;
  border-radius: 8px;
  border: none;
  background: #e53e3e;
  color: #fff;
  font-size: 14px;
  cursor: pointer;
}

.confirm-ok:hover:not(:disabled) { background: #c53030; }
.confirm-ok:disabled { opacity: 0.6; cursor: not-allowed; }

.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.overlay-text {
  background: #fff;
  padding: 20px 32px;
  border-radius: 12px;
  font-size: 16px;
  color: #333;
}
</style>
