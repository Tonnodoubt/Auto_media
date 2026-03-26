<template>
  <div class="outline-preview">
    <div class="meta-card">
      <h2>{{ meta.title }}</h2>
      <div class="meta-tags">
        <span class="tag">{{ meta.genre }}</span>
        <span class="tag">共 {{ meta.episodes }} 集</span>
      </div>
      <p class="theme">{{ meta.theme }}</p>
    </div>

    <div class="section">
      <div class="section-header">
        <h3>主要角色 <span class="hint-text">双击可编辑</span></h3>
      </div>
      <div class="characters">
        <div
          v-for="c in characters"
          :key="c.id || c.name"
          class="char-card"
          :class="{ editing: editingChar === (c.id || c.name) }"
        >
          <div class="char-header">
            <div class="char-main" @dblclick="startEditChar(c)">
              <template v-if="editingChar === (c.id || c.name)">
                <div class="char-edit-row">
                  <span class="char-name-static">{{ c.name }}</span>
                  <span class="char-role">{{ c.role }}</span>
                </div>
                <textarea v-model="editCharDesc" class="edit-char-desc" rows="2" @keydown.esc="cancelEditChar" />
                <div class="edit-actions">
                  <button class="save-btn" @click="saveEditChar(c)">保存</button>
                  <button class="cancel-btn" @click="cancelEditChar">取消</button>
                </div>
              </template>
              <template v-else>
                <div class="char-name">{{ c.name }} <span class="char-role">{{ c.role }}</span></div>
                <div class="char-desc">{{ c.description }}</div>
              </template>
            </div>
            <button class="ai-icon-btn" @click="openCharacterChat(c)" title="AI 修改此角色">✦</button>
          </div>
        </div>
      </div>
    </div>

    <div class="section">
      <h3>剧情大纲 <span class="hint-text">双击可编辑</span></h3>
      <div class="outline-list">
        <div
          v-for="ep in outline"
          :key="ep.episode"
          class="ep-item"
          :class="{ editing: editingEp === ep.episode }"
        >
          <div class="ep-left">
            <div class="ep-num">第 {{ ep.episode }} 集</div>
          </div>
          <div class="ep-content" @dblclick="startEdit(ep)">
            <template v-if="editingEp === ep.episode">
              <input v-model="editTitle" class="edit-title" @keydown.enter="saveEdit" @keydown.esc="cancelEdit" />
              <textarea v-model="editSummary" class="edit-summary" rows="3" @keydown.esc="cancelEdit" />
              <div class="edit-actions">
                <button class="save-btn" @click="saveEdit">保存</button>
                <button class="cancel-btn" @click="cancelEdit">取消</button>
              </div>
            </template>
            <template v-else>
              <div class="ep-title">{{ ep.title }}</div>
              <div class="ep-summary">{{ ep.summary }}</div>
            </template>
          </div>
          <button class="ai-icon-btn" @click="openEpisodeChat(ep)" title="AI 修改此集">✦</button>
        </div>
      </div>
    </div>

    <CharacterChatPanel
      :show="characterChatOpen"
      :character="selectedCharacter"
      @close="characterChatOpen = false"
    />
    <EpisodeChatPanel
      :show="episodeChatOpen"
      :episode="selectedEpisode"
      @close="episodeChatOpen = false"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useStoryStore } from '../stores/story.js'
import { patchStory, refineStory } from '../api/story.js'
import CharacterChatPanel from './CharacterChatPanel.vue'
import EpisodeChatPanel from './EpisodeChatPanel.vue'
import { findCharacterByRef, getCharacterKey } from '../utils/character.js'

defineProps({ meta: Object, characters: Array, outline: Array })

const store = useStoryStore()
const editingEp = ref(null)
const editTitle = ref('')
const editSummary = ref('')
const editingChar = ref(null)
const editCharDesc = ref('')
const characterChatOpen = ref(false)
const selectedCharacter = ref(null)
const episodeChatOpen = ref(false)
const selectedEpisode = ref(null)

function startEdit(ep) {
  editingEp.value = ep.episode
  editTitle.value = ep.title
  editSummary.value = ep.summary
}

async function saveEdit() {
  const ep = store.outline.find(e => e.episode === editingEp.value)
  if (!ep) return
  const oldSummary = ep ? ep.summary : ''
  const epNum = editingEp.value
  const nextOutline = store.outline.map(item => (
    item.episode === epNum
      ? { ...item, title: editTitle.value, summary: editSummary.value }
      : item
  ))

  try {
    const patchResult = await patchStory(store.storyId, { outline: nextOutline })
    if (!patchResult) throw new Error('patch story failed')
    store.updateOutlineEpisode(epNum, editTitle.value, editSummary.value)
    editingEp.value = null
    const res = await refineStory(
      store.storyId,
      'episode',
      `第${epNum}集剧情从「${oldSummary}」改为「${editSummary.value}」`
    )
    if (res) store.applyRefine(res)
  } catch (error) {
    console.error('[OutlinePreview] saveEdit 失败:', error)
  }
}

function cancelEdit() {
  editingEp.value = null
}

function startEditChar(c) {
  editingChar.value = getCharacterKey(c)
  editCharDesc.value = c.description
}

async function saveEditChar(character) {
  if (!character?.id) {
    return
  }
  const key = character.id
  const c = findCharacterByRef(store.characters, character)
  const oldDesc = c ? c.description : ''
  const nextCharacters = store.characters.map(item => (
    item.id === key
      ? { ...item, description: editCharDesc.value }
      : item
  ))

  try {
    const patchResult = await patchStory(store.storyId, { characters: nextCharacters })
    if (!patchResult) throw new Error('patch story failed')
    store.updateCharacter(key, { description: editCharDesc.value })
    editingChar.value = null
    const res = await refineStory(
      store.storyId,
      'character',
      `角色「${character.name}」描述从「${oldDesc}」改为「${editCharDesc.value}」`
    )
    if (res) store.applyRefine(res)
  } catch (error) {
    console.error('[OutlinePreview] saveEditChar 失败:', error)
  }
}

function cancelEditChar() {
  editingChar.value = null
}

function openCharacterChat(character) {
  selectedCharacter.value = character
  characterChatOpen.value = true
}

function openEpisodeChat(episode) {
  selectedEpisode.value = episode
  episodeChatOpen.value = true
}
</script>

<style scoped>
.outline-preview { display: flex; flex-direction: column; gap: 20px; }
.meta-card {
  background: linear-gradient(135deg, #6c63ff, #a78bfa);
  color: #fff;
  border-radius: 16px;
  padding: 20px;
}
.meta-card h2 { font-size: 22px; margin-bottom: 10px; }
.meta-tags { display: flex; gap: 8px; margin-bottom: 10px; }
.tag {
  background: rgba(255,255,255,0.2);
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 12px;
}
.theme { font-size: 14px; opacity: 0.9; line-height: 1.6; }
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.section h3 { font-size: 16px; font-weight: 600; color: #333; display: flex; align-items: center; gap: 8px; }
.hint-text { font-size: 11px; color: #bbb; font-weight: 400; }
.characters { display: flex; flex-direction: column; gap: 10px; }
.char-card {
  background: #fff;
  border-radius: 10px;
  padding: 12px 16px;
  border-left: 4px solid #6c63ff;
  transition: box-shadow 0.2s, border-color 0.2s;
  border: 2px solid transparent;
  border-left: 4px solid #6c63ff;
}
.char-card:hover { box-shadow: 0 2px 10px rgba(108,99,255,0.1); }
.char-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.char-main {
  flex: 1;
  cursor: pointer;
}
.char-edit-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.char-name-static { font-weight: 600; font-size: 15px; white-space: nowrap; }
.edit-char-role {
  font-size: 12px;
  border: 1.5px solid #6c63ff;
  border-radius: 10px;
  padding: 2px 8px;
  color: #6c63ff;
  font-family: inherit;
  outline: none;
  width: 100px;
}
.edit-char-desc {
  width: 100%;
  font-size: 13px;
  color: #444;
  border: 1.5px solid #d0c8ff;
  border-radius: 6px;
  padding: 6px 8px;
  resize: none;
  font-family: inherit;
  line-height: 1.5;
  outline: none;
}
.edit-char-desc:focus { border-color: #6c63ff; }
.char-name { font-weight: 600; font-size: 15px; margin-bottom: 4px; }
.char-role {
  font-size: 12px;
  color: #6c63ff;
  background: #f0eeff;
  padding: 2px 8px;
  border-radius: 10px;
  margin-left: 8px;
  font-weight: 400;
}
.char-desc { font-size: 13px; color: #666; }
.ai-icon-btn {
  padding: 4px 8px;
  background: linear-gradient(135deg, #6c63ff, #a78bfa);
  color: #fff;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 0.2s, transform 0.2s;
  flex-shrink: 0;
}
.ai-icon-btn:hover { opacity: 1; transform: scale(1.1); }
.outline-list { display: flex; flex-direction: column; gap: 8px; }
.ep-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  background: #fff;
  border-radius: 10px;
  padding: 12px 16px;
  transition: box-shadow 0.2s, border-color 0.2s;
  border: 2px solid transparent;
}
.ep-item:hover { box-shadow: 0 2px 10px rgba(108,99,255,0.1); border-color: #e0d9ff; }
.ep-left { flex-shrink: 0; padding-top: 2px; }
.ep-num {
  font-size: 12px;
  color: #6c63ff;
  font-weight: 600;
  white-space: nowrap;
}
.ep-content { flex: 1; min-width: 0; cursor: pointer; }
.ep-title { font-weight: 600; font-size: 14px; margin-bottom: 4px; }
.ep-summary { font-size: 13px; color: #666; line-height: 1.5; }
.edit-title {
  width: 100%;
  font-size: 14px;
  font-weight: 600;
  border: 1.5px solid #6c63ff;
  border-radius: 6px;
  padding: 4px 8px;
  margin-bottom: 6px;
  font-family: inherit;
  outline: none;
}
.edit-summary {
  width: 100%;
  font-size: 13px;
  color: #444;
  border: 1.5px solid #d0c8ff;
  border-radius: 6px;
  padding: 6px 8px;
  resize: none;
  font-family: inherit;
  line-height: 1.5;
  outline: none;
}
.edit-summary:focus, .edit-title:focus { border-color: #6c63ff; }
.edit-actions { display: flex; gap: 8px; margin-top: 8px; justify-content: flex-end; }
.save-btn {
  padding: 5px 14px;
  background: #6c63ff;
  color: #fff;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.save-btn:hover { background: #5a52e0; }
.cancel-btn {
  padding: 5px 14px;
  background: #fff;
  color: #888;
  border: 1.5px solid #e0e0e0;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}
.cancel-btn:hover { border-color: #aaa; }
</style>
