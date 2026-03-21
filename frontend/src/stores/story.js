import { defineStore } from 'pinia'

export const useStoryStore = defineStore('story', {
  state: () => ({
    currentStep: 1,
    storyId: null,
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
    usage: { prompt_tokens: 0, completion_tokens: 0 },
    wbHistory: [],
    wbTurn: 0,
    wbCurrentQuestion: null,
  }),
  getters: {
    totalTokens: (state) => state.usage.prompt_tokens + state.usage.completion_tokens,
  },
  actions: {
    setSelectedSetting(val) { this.selectedSetting = val },
    setStep(n) { this.currentStep = n },
    setInput(idea, genre, tone) { this.input = { idea, genre, tone } },
    setAnalyzeResult({ story_id, analysis, suggestions, placeholder, usage }) {
      this.storyId = story_id
      this.analysis = analysis
      this.suggestions = suggestions
      this.placeholder = placeholder
      if (usage) {
        this.usage.prompt_tokens += usage.prompt_tokens
        this.usage.completion_tokens += usage.completion_tokens
      }
    },
    setOutlineResult({ story_id, meta, characters, relationships, outline, usage }) {
      this.storyId = story_id
      this.meta = meta
      this.characters = characters
      this.relationships = relationships || []
      this.outline = outline
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
    resetScenes() { this.scenes = [] },
    updateOutlineEpisode(episode, title, summary) {
      const ep = this.outline.find(e => e.episode === episode)
      if (ep) { ep.title = title; ep.summary = summary }
    },
    updateCharacter(name, description) {
      const c = this.characters.find(c => c.name === name)
      if (c) { c.description = description }
    },
    applyRefine({ relationships, outline, meta_theme, usage }) {
      if (relationships) this.relationships = relationships
      if (outline) this.outline = outline
      if (meta_theme && this.meta) this.meta.theme = meta_theme
      if (usage) {
        this.usage.prompt_tokens += usage.prompt_tokens
        this.usage.completion_tokens += usage.completion_tokens
      }
    },
    setWorldBuildingStart({ story_id, turn, question, usage }) {
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
