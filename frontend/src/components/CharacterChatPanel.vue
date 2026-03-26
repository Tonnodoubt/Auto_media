<template>
  <div v-if="show" class="overlay" @click="$emit('close')" />
  <div class="panel" :class="{ open: show }">
    <div class="panel-header">
      <span>角色 AI 修改助手</span>
      <button class="close-btn" @click="$emit('close')">✕</button>
    </div>

    <div v-if="character" class="character-info">
      <div class="char-name">{{ character.name }}</div>
      <div class="char-role">{{ character.role }}</div>
    </div>

    <div class="chat-history" ref="historyEl">
      <div v-if="messages.length === 0" class="empty-hint">
        告诉我你想怎么修改这个角色，比如：<br>「让他更冷酷一些」
      </div>
      <div v-for="(msg, i) in messages" :key="i" :class="['bubble', msg.role]">
        <template v-if="msg.role === 'ai' && getAiSections(msg).length">
          <div class="bubble-text bubble-sections">
            <div v-for="section in getAiSections(msg)" :key="section.key" class="section-block">
              <div class="section-title">{{ section.title }}</div>
              <div v-for="(item, idx) in section.items" :key="`${section.key}-${idx}`" class="section-item">
                {{ item }}
              </div>
            </div>
          </div>
        </template>
        <div v-else class="bubble-text">{{ msg.text }}</div>
      </div>
      <div v-if="streaming" class="bubble ai">
        <div class="bubble-text streaming">{{ streamingDisplayText }}<span class="cursor">|</span></div>
      </div>
    </div>

    <div class="input-area">
      <textarea
        v-model="input"
        placeholder="描述你想修改的内容..."
        rows="3"
        @keydown.enter.exact.prevent="send"
      />
      <button class="send-btn" :disabled="!input.trim() || streaming || applying" @click="send">
        {{ streaming ? '思考中...' : '发送' }}
      </button>
      <button
        class="confirm-btn"
        :disabled="!hasAiReply || streaming || applying"
        @click="confirmApply"
      >
        {{ applying ? '应用中...' : '确认应用' }}
      </button>
    </div>
    <div v-if="error" class="error-tip">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, computed } from 'vue'
import { useStoryStore } from '../stores/story.js'
import { streamChat, applyChatChanges, refineStory } from '../api/story.js'
import { findCharacterByRef } from '../utils/character.js'
import { normalizeChatText, parseCharacterChatSections } from '../utils/storyChat.js'

const props = defineProps({ show: Boolean, character: Object })
const emit = defineEmits(['close'])

const store = useStoryStore()
const messages = ref([])
const input = ref('')
const streaming = ref(false)
const streamingText = ref('')
const applying = ref(false)
const error = ref('')
const historyEl = ref(null)

const hasAiReply = computed(() => messages.value.some(m => m.role === 'ai'))
const streamingDisplayText = computed(() => normalizeChatText(streamingText.value))

function getAiSections(msg) {
  return parseCharacterChatSections(msg?.text || '')
}

function buildCharacterRefineSummary(currentChar, previousDescription, nextDescription) {
  const latestAiReply = [...messages.value].reverse().find(message => message.role === 'ai')
  const storyImpactSection = getAiSections(latestAiReply).find(section => section.key === 'story_impact')
  const storyImpactText = storyImpactSection?.items?.length
    ? `；建议同步处理的局部剧情影响：${storyImpactSection.items.join('；')}`
    : ''

  return `角色「${currentChar.name}」描述从「${previousDescription}」改为「${nextDescription}」${storyImpactText}`
}

async function scrollToBottom() {
  await nextTick()
  if (historyEl.value) historyEl.value.scrollTop = historyEl.value.scrollHeight
}

watch(() => messages.value.length, scrollToBottom)
watch(streamingText, scrollToBottom)

watch(() => props.character?.id || props.character?.name, () => {
  messages.value = []
  input.value = ''
  error.value = ''
})

async function send() {
  const text = input.value.trim()
  if (!text || streaming.value || applying.value || !props.character) return
  input.value = ''
  error.value = ''
  messages.value = [...messages.value, { role: 'user', text }]

  streaming.value = true
  streamingText.value = ''

  await streamChat(
    store.storyId,
    {
      message: text,
      mode: 'character',
      context: {
        character: {
          id: props.character.id,
          name: props.character.name,
          role: props.character.role,
          description: props.character.description,
        },
        outline: store.outline,
      },
    },
    (chunk) => { streamingText.value += chunk },
    () => {
      streaming.value = false
      const aiText = normalizeChatText(streamingText.value)
      messages.value = [...messages.value, {
        role: 'ai',
        text: aiText,
      }]
      streamingText.value = ''
    },
    (msg) => {
      streaming.value = false
      streamingText.value = ''
      error.value = msg || 'AI 响应失败，请重试'
    }
  )
}

async function confirmApply() {
  if (!props.character || applying.value) return
  if (!props.character.id) {
    error.value = '角色 ID 缺失，无法安全应用修改，请重新生成或刷新后重试'
    return
  }
  applying.value = true
  error.value = ''
  try {
    // 从 store 取最新数据，避免 props 陈旧
    const currentChar = findCharacterByRef(store.characters, props.character)
    if (!currentChar?.id) {
      error.value = '未找到带 ID 的最新角色数据，已阻止按名字误匹配'
      return
    }
    const res = await applyChatChanges(
      store.storyId,
      'character',
      messages.value,
      { id: currentChar.id, name: currentChar.name, role: currentChar.role, description: currentChar.description },
      store.characters,
      null
    )
    if (!res?.description) {
      error.value = '未能获取角色描述修改结果，请重试'
      return
    }
    const previousDescription = currentChar.description
    const nextDescription = res.description ?? currentChar.description
    store.updateCharacter(currentChar.id, {
      description: nextDescription,
    })
    if (nextDescription !== previousDescription) {
      let refineRes = null
      try {
        refineRes = await refineStory(
          store.storyId,
          'character',
          buildCharacterRefineSummary(currentChar, previousDescription, nextDescription)
        )
      } catch (refineError) {
        console.error('[CharacterChatPanel] refineStory 失败:', refineError)
        error.value = '角色描述已更新，但剧情联动失败，请重试'
        return
      }
      if (!refineRes) {
        console.error('[CharacterChatPanel] refineStory 返回空结果')
        error.value = '角色描述已更新，但剧情联动失败，请重试'
        return
      }
      store.applyRefine(refineRes)
    }
    messages.value = []
    input.value = ''
    emit('close')
  } catch (e) {
    console.error('[CharacterChatPanel] confirmApply 失败:', e)
    error.value = `应用失败：${e?.message || '请重试'}`
  } finally {
    applying.value = false
  }
}
</script>

<style scoped>
.overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.2); z-index: 100;
}
.panel {
  position: fixed; top: 0; right: 0; width: 360px; height: 100vh;
  background: #fff; box-shadow: -4px 0 24px rgba(0,0,0,0.12); z-index: 101;
  display: flex; flex-direction: column;
  transform: translateX(100%); transition: transform 0.3s ease;
}
.panel.open { transform: translateX(0); }
.panel-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px; border-bottom: 1px solid #f0f0f0;
  font-size: 15px; font-weight: 600; color: #333;
}
.close-btn { background: none; border: none; font-size: 16px; color: #aaa; cursor: pointer; padding: 4px; }
.close-btn:hover { color: #555; }
.character-info { padding: 12px 16px; background: #f0eeff; border-bottom: 1px solid #e0d9ff; }
.char-name { font-size: 14px; font-weight: 600; color: #6c63ff; margin-bottom: 4px; }
.char-role { font-size: 12px; color: #888; }
.chat-history {
  flex: 1; overflow-y: auto; padding: 16px;
  display: flex; flex-direction: column; gap: 12px;
}
.empty-hint { color: #bbb; font-size: 13px; line-height: 1.8; text-align: center; margin-top: 40px; }
.bubble { max-width: 90%; display: flex; flex-direction: column; gap: 6px; }
.bubble.user { align-self: flex-end; }
.bubble.ai { align-self: flex-start; }
.bubble-text { padding: 10px 14px; border-radius: 14px; font-size: 13px; line-height: 1.6; white-space: pre-wrap; }
.bubble.user .bubble-text { background: #6c63ff; color: #fff; border-bottom-right-radius: 4px; }
.bubble.ai .bubble-text { background: #f5f5f7; color: #333; border-bottom-left-radius: 4px; }
.bubble-sections { display: flex; flex-direction: column; gap: 10px; }
.section-block { display: flex; flex-direction: column; gap: 6px; }
.section-title { font-size: 12px; font-weight: 700; color: #6c63ff; }
.section-item { position: relative; padding-left: 12px; color: #444; }
.section-item::before {
  content: '•';
  position: absolute;
  left: 0;
  top: 0;
  color: #8f86ff;
}
.streaming { color: #888; }
.cursor { animation: blink 1s infinite; }
@keyframes blink { 0%,100% { opacity: 1 } 50% { opacity: 0 } }
.input-area {
  padding: 12px 16px; border-top: 1px solid #f0f0f0;
  display: flex; flex-direction: column; gap: 8px;
}
textarea {
  width: 100%; padding: 10px 14px; border-radius: 10px;
  border: 2px solid #e0e0e0; font-size: 13px; resize: none;
  line-height: 1.6; font-family: inherit; transition: border-color 0.2s;
}
textarea:focus { border-color: #6c63ff; outline: none; }
.send-btn {
  padding: 10px; background: #6c63ff; color: #fff;
  border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;
}
.send-btn:hover:not(:disabled) { background: #5a52e0; }
.send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.confirm-btn {
  padding: 10px; background: #6c63ff; color: #fff;
  border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;
}
.confirm-btn:hover:not(:disabled) { background: #5a52e0; }
.confirm-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.error-tip { padding: 0 16px 12px; color: #e53935; font-size: 12px; }
</style>
