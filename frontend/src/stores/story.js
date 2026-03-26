import { defineStore } from 'pinia'
import { findCharacterByRef, getCharacterKey } from '../utils/character.js'

function mergeCharacters(existingCharacters = [], incomingCharacters = []) {
  const incomingMap = new Map(
    incomingCharacters
      .filter(character => getCharacterKey(character))
      .map(character => [getCharacterKey(character), character])
  )

  const merged = existingCharacters.map(character => {
    const next = incomingMap.get(getCharacterKey(character))
    if (!next) return character
    incomingMap.delete(getCharacterKey(character))
    return { ...character, ...next }
  })

  incomingMap.forEach(character => {
    merged.push(character)
  })

  return merged
}

export const useStoryStore = defineStore('story', {
  persist: true,
  state: () => ({
    currentStep: 1,
    storyId: null,
    manualProjectId: '',
    manualPipelineId: '',
    manualStoryId: '',
    input: { idea: '', genre: '', tone: '' },
    analysis: '',
    suggestions: [],
    placeholder: '',
    selectedSetting: '',
    meta: null,
    characters: [],
    relationships: [],
    outline: [],
    scenes: [],
    step3Done: false,
    shots: [],
    usage: { prompt_tokens: 0, completion_tokens: 0 },
    characterImages: {},
    artStyle: '',
    wbHistory: [],
    wbTurn: 0,
    wbCurrentQuestion: null,
  }),
  getters: {
    totalTokens: (state) => state.usage.prompt_tokens + state.usage.completion_tokens,
  },
  actions: {
    startNewStory(idea = '') {
      this.$reset()
      this.input.idea = idea
      this.currentStep = 1
    },
    setManualPipelineContext({ projectId = '', pipelineId = '', storyId = '' } = {}) {
      if (projectId) this.manualProjectId = projectId
      if (pipelineId) this.manualPipelineId = pipelineId
      if (storyId) this.manualStoryId = storyId
    },
    clearManualPipelineContext({ keepProjectId = '', keepStoryId = '' } = {}) {
      this.manualProjectId = keepProjectId || ''
      this.manualPipelineId = ''
      this.manualStoryId = keepStoryId || ''
    },
    setSelectedSetting(val) { this.selectedSetting = val },
    setArtStyle(val) {
      if (typeof val !== 'string') {
        this.artStyle = ''
        return
      }
      const normalized = val.trim()
      this.artStyle = normalized.length ? normalized : ''
    },
    setStep(n) { this.currentStep = n },
    setInput(idea, genre, tone) { this.input = { idea, genre, tone } },
    setAnalyzeResult({ story_id, analysis, suggestions, placeholder, usage }) {
      if (story_id && story_id !== this.storyId) {
        this.clearManualPipelineContext({
          keepProjectId: story_id,
          keepStoryId: story_id,
        })
      }
      this.storyId = story_id
      this.analysis = analysis
      this.suggestions = suggestions
      this.placeholder = placeholder
      if (usage) {
        this.usage.prompt_tokens += usage.prompt_tokens
        this.usage.completion_tokens += usage.completion_tokens
      }
    },
    invalidateGeneratedScript({ keepProjectId = '', keepStoryId = '' } = {}) {
      this.scenes = []
      this.shots = []
      this.step3Done = false
      this.clearManualPipelineContext({
        keepProjectId: keepProjectId || this.storyId || '',
        keepStoryId: keepStoryId || this.storyId || '',
      })
    },
    setOutlineResult({ story_id, meta, characters, relationships, outline, usage }) {
      if (story_id && story_id !== this.storyId) {
        this.clearManualPipelineContext({
          keepProjectId: story_id,
          keepStoryId: story_id,
        })
      }
      this.storyId = story_id
      this.invalidateGeneratedScript({
        keepProjectId: story_id || '',
        keepStoryId: story_id || '',
      })
      if (meta != null) this.meta = meta
      if (characters != null && characters.length > 0) this.characters = characters
      if (relationships != null && relationships.length > 0) this.relationships = relationships
      if (outline != null && outline.length > 0) this.outline = outline
      if (usage) {
        this.usage.prompt_tokens += usage.prompt_tokens
        this.usage.completion_tokens += usage.completion_tokens
      }
    },
    addScene(scene) {
      if (scene.__usage__) {
        this.usage.prompt_tokens += scene.__usage__.prompt_tokens
        this.usage.completion_tokens += scene.__usage__.completion_tokens
      } else {
        this.scenes.push(scene)
      }
    },
    resetScenes() {
      this.invalidateGeneratedScript({
        keepProjectId: this.storyId || '',
        keepStoryId: this.storyId || '',
      })
    },
    setShots(shots) {
      this.shots = shots.map(s => ({ ...s, ttsLoading: false, imageLoading: false, videoLoading: false }))
    },
    clearShots() { this.shots = [] },
    updateOutlineEpisode(episode, title, summary) {
      const ep = this.outline.find(e => e.episode === episode)
      if (ep) {
        ep.title = title
        ep.summary = summary
        this.invalidateGeneratedScript()
      }
    },
    updateCharacter(characterId, fields = {}) {
      const c = findCharacterByRef(this.characters, { id: characterId })
      if (c) {
        Object.assign(c, fields)
        this.invalidateGeneratedScript()
      }
    },
    applyRefine({ characters, relationships, outline, meta_theme, usage }) {
      const touchedNarrative = (
        (characters != null && characters.length > 0)
        || (outline != null && outline.length > 0)
      )
      if (touchedNarrative) {
        this.invalidateGeneratedScript()
      }
      if (characters != null && characters.length > 0) {
        this.characters = mergeCharacters(this.characters, characters)
      }
      if (relationships != null && relationships.length > 0) this.relationships = relationships
      if (outline != null && outline.length > 0) {
        // Merge by episode: a partial LLM response must not wipe out unlisted episodes
        const epMap = Object.fromEntries(outline.map(ep => [ep.episode, ep]))
        this.outline = this.outline.map(ep => epMap[ep.episode] ?? ep)
      }
      if (meta_theme && this.meta) this.meta.theme = meta_theme
      if (usage) {
        this.usage.prompt_tokens += usage.prompt_tokens
        this.usage.completion_tokens += usage.completion_tokens
      }
    },
    loadStory(storyData) {
      // 从服务器数据恢复完整 store 状态（用于历史剧本恢复）
      this.$reset()
      this.storyId = storyData.id
      this.clearManualPipelineContext({
        keepProjectId: storyData.id || '',
        keepStoryId: storyData.id || '',
      })
      this.input = {
        idea: storyData.idea || '',
        genre: storyData.genre || '',
        tone: storyData.tone || '',
      }
      this.selectedSetting = storyData.selected_setting || ''
      this.meta = storyData.meta || null
      this.characters = storyData.characters || []
      this.relationships = storyData.relationships || []
      this.outline = storyData.outline || []
      this.scenes = storyData.scenes || []
      this.characterImages = storyData.character_images || {}
      this.setArtStyle(storyData.art_style || '')
      this.wbHistory = storyData.wb_history || []
      this.wbTurn = storyData.wb_turn || 0
      this.step3Done = (storyData.scenes || []).length > 0
      if (this.step3Done) {
        this.currentStep = 4
      } else if ((storyData.characters || []).length > 0) {
        this.currentStep = 3
      } else {
        this.currentStep = 2
      }
    },
    setWorldBuildingStart({ story_id, turn, question, usage }) {
      // Only wipe story data when the story_id has actually changed
      if (story_id !== this.storyId) {
        this.meta = null
        this.characters = []
        this.relationships = []
        this.outline = []
        this.scenes = []
        this.shots = []
        this.step3Done = false
        this.selectedSetting = ''
        this.artStyle = ''
        this.clearManualPipelineContext({
          keepProjectId: story_id || '',
          keepStoryId: story_id || '',
        })
      }
      this.storyId = story_id
      this.wbTurn = turn
      this.wbCurrentQuestion = question
      this.wbHistory = question ? [{ role: 'ai', text: question.text, type: question.type, options: question.options }] : []
      if (usage) {
        this.usage.prompt_tokens += usage.prompt_tokens
        this.usage.completion_tokens += usage.completion_tokens
      }
    },
    appendWbTurn({ turn, question, status, world_summary, answer, usage }) {
      this.wbTurn = turn
      const newHistory = [
        ...this.wbHistory,
        { role: 'user', text: answer },
      ]
      if (question) newHistory.push({ role: 'ai', text: question.text, type: question.type, options: question.options })
      this.wbHistory = newHistory
      this.wbCurrentQuestion = question || null
      if (status === 'complete' && world_summary) {
        this.selectedSetting = world_summary
      }
      if (usage) {
        this.usage.prompt_tokens += usage.prompt_tokens
        this.usage.completion_tokens += usage.completion_tokens
      }
    },
  },
})
