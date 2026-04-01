import { defineStore } from 'pinia'
import { findCharacterByRef, getCharacterKey } from '../utils/character.js'

export function getSceneKey(episode, sceneNumber) {
  return `ep${String(episode).padStart(2, '0')}_scene${String(sceneNumber).padStart(2, '0')}`
}

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

function createEmptySceneReferenceAsset() {
  return {
    status: 'idle',
    variants: {
      scene: null,
    },
    error: '',
    updated_at: '',
  }
}

function escapeXml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

function buildVariantSvg({ title, subtitle, variant, accent, sceneKey }) {
  const safeTitle = escapeXml(String(title || 'Scene Key Art').slice(0, 48))
  const safeSubtitle = escapeXml(String(subtitle || '').slice(0, 72))
  const safeVariant = escapeXml(String(variant || 'scene').toUpperCase())
  const safeKey = escapeXml(String(sceneKey || '').slice(0, 24))
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">
      <defs>
        <linearGradient id="bg" x1="0%" x2="100%" y1="0%" y2="100%">
          <stop offset="0%" stop-color="${accent[0]}"/>
          <stop offset="100%" stop-color="${accent[1]}"/>
        </linearGradient>
      </defs>
      <rect width="960" height="540" rx="28" fill="url(#bg)"/>
      <circle cx="786" cy="120" r="122" fill="rgba(255,255,255,0.08)"/>
      <circle cx="170" cy="438" r="158" fill="rgba(255,255,255,0.06)"/>
      <rect x="56" y="56" width="200" height="40" rx="20" fill="rgba(10,14,25,0.26)"/>
      <text x="82" y="82" fill="#ffffff" font-size="22" font-family="Arial, sans-serif" letter-spacing="2">${safeVariant}</text>
      <text x="56" y="304" fill="#ffffff" font-size="42" font-family="Arial, sans-serif" font-weight="700">${safeTitle}</text>
      <text x="56" y="350" fill="rgba(255,255,255,0.9)" font-size="22" font-family="Arial, sans-serif">${safeSubtitle}</text>
      <text x="56" y="476" fill="rgba(255,255,255,0.75)" font-size="18" font-family="Arial, sans-serif">${safeKey}</text>
      <rect x="56" y="398" width="312" height="6" rx="3" fill="rgba(255,255,255,0.30)"/>
      <rect x="56" y="398" width="174" height="6" rx="3" fill="#ffffff"/>
    </svg>
  `.trim()
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`
}

function createMockSceneReferenceAsset(sceneKey, scene = {}) {
  const title = scene.environment || scene.visual || 'Episode Environment Pack'
  const subtitle = 'Main environment only, keep layout, lighting, and color simple'
  const variants = {
    scene: {
      label: 'scene',
      prompt: `Environment key art for ${title}. Focus on the primary space, stable layout, and simple lighting. Avoid characters, action, and excessive detail.`,
      image_url: buildVariantSvg({
        title,
        subtitle,
        variant: 'scene',
        accent: ['#304d7d', '#8ba8d8'],
        sceneKey,
      }),
    },
  }
  return {
    status: 'ready',
    variants,
    error: '',
    updated_at: new Date().toISOString(),
  }
}

function cloneAsset(asset = {}) {
  return {
    status: asset.status || 'idle',
    variants: {
      scene: asset.variants?.scene || null,
    },
    error: asset.error || '',
    updated_at: asset.updated_at || '',
    ...(asset.environment_pack_key ? { environment_pack_key: asset.environment_pack_key } : {}),
    ...(asset.group_index ? { group_index: asset.group_index } : {}),
    ...(asset.group_label ? { group_label: asset.group_label } : {}),
    ...(Array.isArray(asset.affected_scene_keys) ? { affected_scene_keys: [...asset.affected_scene_keys] } : {}),
    ...(Array.isArray(asset.affected_scene_numbers) ? { affected_scene_numbers: [...asset.affected_scene_numbers] } : {}),
    ...(asset.episode_title ? { episode_title: asset.episode_title } : {}),
    ...(asset.summary_environment ? { summary_environment: asset.summary_environment } : {}),
    ...(asset.summary_lighting ? { summary_lighting: asset.summary_lighting } : {}),
    ...(asset.summary_mood ? { summary_mood: asset.summary_mood } : {}),
    ...(Array.isArray(asset.summary_visuals) ? { summary_visuals: [...asset.summary_visuals] } : {}),
  }
}

function hydrateSceneReferenceAssets(meta = {}, scenes = []) {
  const explicitSceneAssets = meta?.scene_reference_assets || {}
  if (Object.keys(explicitSceneAssets).length > 0) {
    return explicitSceneAssets
  }

  const episodeAssets = meta?.episode_reference_assets || {}
  const hydrated = {}
  Object.values(episodeAssets).forEach(asset => {
    ;(asset?.affected_scene_keys || []).forEach(sceneKey => {
      hydrated[sceneKey] = cloneAsset(asset)
    })
  })
  return hydrated
}

function hydrateStoryboardGeneration(meta = {}) {
  const generation = meta?.storyboard_generation
  if (!generation || typeof generation !== 'object') {
    return {
      shots: [],
      projectId: '',
      pipelineId: '',
      storyId: '',
      finalVideoUrl: '',
    }
  }
  return {
    shots: Array.isArray(generation.shots) ? generation.shots.map(shot => ({ ...shot })) : [],
    projectId: generation.project_id || '',
    pipelineId: generation.pipeline_id || '',
    storyId: generation.story_id || '',
    finalVideoUrl: generation.final_video_url || '',
  }
}

function sanitizeStoryboardShot(shot = {}) {
  if (!shot || typeof shot !== 'object') return {}
  const {
    ttsLoading,
    imageLoading,
    videoLoading,
    last_frame_url: deprecatedLastFrameUrl,
    last_frame_prompt: deprecatedLastFramePrompt,
    ...persistedFields
  } = shot
  void deprecatedLastFrameUrl
  void deprecatedLastFramePrompt
  return { ...persistedFields }
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
    storyboardFinalVideoUrl: '',
    usage: { prompt_tokens: 0, completion_tokens: 0 },
    characterImages: {},
    sceneReferenceAssets: {},
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
      this.syncStoryboardGenerationMeta({
        projectId: this.manualProjectId,
        pipelineId: this.manualPipelineId,
        storyId: this.manualStoryId,
      })
    },
    clearManualPipelineContext({ keepProjectId = '', keepStoryId = '' } = {}) {
      this.manualProjectId = keepProjectId || ''
      this.manualPipelineId = ''
      this.manualStoryId = keepStoryId || ''
      this.syncStoryboardGenerationMeta({
        projectId: this.manualProjectId,
        pipelineId: '',
        storyId: this.manualStoryId,
      })
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
      this.clearShots()
      this.sceneReferenceAssets = {}
      if (this.meta && typeof this.meta === 'object') {
        this.meta = {
          ...this.meta,
          scene_reference_assets: {},
          episode_reference_assets: {},
        }
      }
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
        this.ensureSceneReferenceAssets()
      }
    },
    resetScenes() {
      this.invalidateGeneratedScript({
        keepProjectId: this.storyId || '',
        keepStoryId: this.storyId || '',
      })
    },
    ensureSceneReferenceAssets() {
      const nextAssets = { ...this.sceneReferenceAssets }
      const validKeys = new Set()
      this.scenes.forEach(episode => {
        episode.scenes?.forEach(scene => {
          const sceneKey = getSceneKey(episode.episode, scene.scene_number)
          validKeys.add(sceneKey)
          if (!nextAssets[sceneKey]) {
            nextAssets[sceneKey] = createEmptySceneReferenceAsset()
          }
        })
      })
      Object.keys(nextAssets).forEach(sceneKey => {
        if (!validKeys.has(sceneKey)) delete nextAssets[sceneKey]
      })
      this.sceneReferenceAssets = nextAssets
    },
    getSceneKey(episode, sceneNumber) {
      return getSceneKey(episode, sceneNumber)
    },
    getEpisodeSceneKeys(episode) {
      const episodeEntry = this.scenes.find(item => item.episode === episode)
      if (!episodeEntry) return []
      return (episodeEntry.scenes || []).map(scene => getSceneKey(episode, scene.scene_number))
    },
    getEpisodeSceneReferenceGroups(episode) {
      const sceneKeys = this.getEpisodeSceneKeys(episode)
      const groups = []
      const seenPackKeys = new Set()
      sceneKeys.forEach(sceneKey => {
        const asset = this.sceneReferenceAssets[sceneKey]
        const packKey = asset?.environment_pack_key
        if (!asset || !packKey || seenPackKeys.has(packKey)) return
        seenPackKeys.add(packKey)
        groups.push(cloneAsset(asset))
      })
      return groups.sort((left, right) => (left.group_index || 0) - (right.group_index || 0))
    },
    getEpisodeSceneReferenceStatus(episode) {
      const groups = this.getEpisodeSceneReferenceGroups(episode)
      if (groups.some(group => group.status === 'loading')) return 'loading'
      if (groups.some(group => group.status === 'failed')) return 'failed'
      if (groups.some(group => group.status === 'stale')) return 'stale'
      if (groups.some(group => group.status === 'idle')) return 'idle'
      if (groups.length > 0 && groups.every(group => group.status === 'ready')) return 'ready'

      const fallbackSceneNumber = this.scenes.find(item => item.episode === episode)?.scenes?.[0]?.scene_number || 1
      const fallbackSceneKey = getSceneKey(episode, fallbackSceneNumber)
      return this.sceneReferenceAssets[fallbackSceneKey]?.status || 'idle'
    },
    setSceneReferenceAsset(sceneKey, asset = {}) {
      const existing = this.sceneReferenceAssets[sceneKey] || createEmptySceneReferenceAsset()
      this.sceneReferenceAssets = {
        ...this.sceneReferenceAssets,
        [sceneKey]: {
          ...existing,
          ...asset,
          variants: {
            ...existing.variants,
            ...(asset.variants || {}),
          },
        },
      }
    },
    setEpisodeSceneReferenceStatus(episode, status, error = '') {
      this.getEpisodeSceneKeys(episode).forEach(sceneKey => {
        this.setSceneReferenceStatus(sceneKey, status, error)
      })
    },
    applyEpisodeSceneReferenceAsset({ episode, groups = [], affectedSceneKeys = [], affected_scene_keys = [], asset = {} } = {}) {
      if (Array.isArray(groups) && groups.length > 0) {
        const episodeSceneKeys = this.getEpisodeSceneKeys(episode)
        episodeSceneKeys.forEach(sceneKey => {
          this.clearSceneReferenceAsset(sceneKey)
        })
        if (this.meta) {
          const nextMeta = { ...this.meta }
          const nextSceneAssets = {
            ...(nextMeta.scene_reference_assets || {}),
          }
          const nextEpisodeAssets = {
            ...(nextMeta.episode_reference_assets || {}),
          }
          Object.keys(nextEpisodeAssets).forEach(packKey => {
            if (packKey.startsWith(`ep${String(episode).padStart(2, '0')}_`)) delete nextEpisodeAssets[packKey]
          })
          Object.keys(nextSceneAssets).forEach(sceneKey => {
            if (sceneKey.startsWith(`ep${String(episode).padStart(2, '0')}_scene`)) delete nextSceneAssets[sceneKey]
          })
          groups.forEach(group => {
            const groupAsset = cloneAsset(group.asset)
            ;(group.affected_scene_keys || []).forEach(sceneKey => {
              this.setSceneReferenceAsset(sceneKey, groupAsset)
              nextSceneAssets[sceneKey] = cloneAsset(groupAsset)
            })
            nextEpisodeAssets[group.environment_pack_key] = cloneAsset(groupAsset)
          })
          nextMeta.scene_reference_assets = nextSceneAssets
          nextMeta.episode_reference_assets = nextEpisodeAssets
          this.meta = nextMeta
        } else {
          groups.forEach(group => {
            const groupAsset = cloneAsset(group.asset)
            ;(group.affected_scene_keys || []).forEach(sceneKey => {
              this.setSceneReferenceAsset(sceneKey, groupAsset)
            })
          })
        }
        return
      }

      const normalizedKeys = affectedSceneKeys.length > 0 ? affectedSceneKeys : affected_scene_keys
      const targetKeys = normalizedKeys.length > 0 ? normalizedKeys : this.getEpisodeSceneKeys(episode)
      targetKeys.forEach(sceneKey => {
        this.setSceneReferenceAsset(sceneKey, cloneAsset(asset))
      })
      if (this.meta) {
        const nextMeta = { ...this.meta }
        const nextSceneAssets = {
          ...(nextMeta.scene_reference_assets || {}),
        }
        targetKeys.forEach(sceneKey => {
          nextSceneAssets[sceneKey] = cloneAsset(asset)
        })
        nextMeta.scene_reference_assets = nextSceneAssets
        if (asset.environment_pack_key) {
          nextMeta.episode_reference_assets = {
            ...(nextMeta.episode_reference_assets || {}),
            [asset.environment_pack_key]: cloneAsset(asset),
          }
        }
        this.meta = nextMeta
      }
    },
    setSceneReferenceStatus(sceneKey, status, error = '') {
      const existing = this.sceneReferenceAssets[sceneKey] || createEmptySceneReferenceAsset()
      this.sceneReferenceAssets = {
        ...this.sceneReferenceAssets,
        [sceneKey]: {
          ...existing,
          status,
          error,
        },
      }
    },
    clearSceneReferenceAsset(sceneKey) {
      const nextAssets = { ...this.sceneReferenceAssets }
      delete nextAssets[sceneKey]
      this.sceneReferenceAssets = nextAssets
    },
    invalidateSceneReferenceAssetsByStoryEdit() {
      const nextAssets = {}
      Object.entries(this.sceneReferenceAssets).forEach(([sceneKey, asset]) => {
        nextAssets[sceneKey] = {
          ...asset,
          status: asset.status === 'ready' ? 'stale' : asset.status,
        }
      })
      this.sceneReferenceAssets = nextAssets
    },
    async generateMockSceneReferenceAsset({ episode, sceneNumber, scene }) {
      const sceneKey = getSceneKey(episode, sceneNumber)
      this.setSceneReferenceStatus(sceneKey, 'loading', '')
      await new Promise(resolve => setTimeout(resolve, 700))
      this.setSceneReferenceAsset(sceneKey, createMockSceneReferenceAsset(sceneKey, scene))
    },
    syncStoryboardGenerationMeta(payload = {}) {
      const currentMeta = this.meta && typeof this.meta === 'object' ? this.meta : {}
      const existingGeneration = currentMeta.storyboard_generation && typeof currentMeta.storyboard_generation === 'object'
        ? currentMeta.storyboard_generation
        : {}
      const nextGeneration = { ...existingGeneration }
      const has = key => Object.prototype.hasOwnProperty.call(payload, key)

      if (has('shots')) {
        nextGeneration.shots = Array.isArray(payload.shots)
          ? payload.shots.map(shot => sanitizeStoryboardShot(shot))
          : []
      }
      if (has('projectId')) nextGeneration.project_id = typeof payload.projectId === 'string' ? payload.projectId : ''
      if (has('pipelineId')) nextGeneration.pipeline_id = typeof payload.pipelineId === 'string' ? payload.pipelineId : ''
      if (has('storyId')) nextGeneration.story_id = typeof payload.storyId === 'string' ? payload.storyId : ''
      if (has('finalVideoUrl')) {
        nextGeneration.final_video_url = typeof payload.finalVideoUrl === 'string' ? payload.finalVideoUrl : ''
      }
      if (has('clearGeneratedFiles') && payload.clearGeneratedFiles) {
        // Parsing/reset flows should drop stale timeline/video artifacts entirely.
        nextGeneration.generated_files = {}
      } else if (has('generatedFiles')) {
        const incomingGeneratedFiles = payload.generatedFiles && typeof payload.generatedFiles === 'object'
          ? payload.generatedFiles
          : {}
        if (has('replaceGeneratedFiles') && payload.replaceGeneratedFiles) {
          nextGeneration.generated_files = {
            ...incomingGeneratedFiles,
          }
        } else {
          const existingGeneratedFiles = nextGeneration.generated_files && typeof nextGeneration.generated_files === 'object'
            ? nextGeneration.generated_files
            : {}
          const mergedGeneratedFiles = { ...existingGeneratedFiles }
          Object.entries(incomingGeneratedFiles).forEach(([key, value]) => {
            if (
              mergedGeneratedFiles[key]
              && typeof mergedGeneratedFiles[key] === 'object'
              && !Array.isArray(mergedGeneratedFiles[key])
              && value
              && typeof value === 'object'
              && !Array.isArray(value)
            ) {
              mergedGeneratedFiles[key] = {
                ...mergedGeneratedFiles[key],
                ...value,
              }
              return
            }
            mergedGeneratedFiles[key] = value
          })
          nextGeneration.generated_files = {
            ...mergedGeneratedFiles,
          }
        }
      }

      this.meta = {
        ...currentMeta,
        storyboard_generation: nextGeneration,
      }
    },
    setShots(shots) {
      const normalizedShots = Array.isArray(shots) ? shots : []
      this.shots = normalizedShots.map(s => ({
        ...sanitizeStoryboardShot(s),
        ttsLoading: false,
        imageLoading: false,
        videoLoading: false,
      }))
      this.syncStoryboardGenerationMeta({ shots: this.shots })
    },
    setStoryboardFinalVideoUrl(url) {
      this.storyboardFinalVideoUrl = typeof url === 'string' ? url : ''
      this.syncStoryboardGenerationMeta({ finalVideoUrl: this.storyboardFinalVideoUrl })
    },
    clearShots() {
      this.shots = []
      this.storyboardFinalVideoUrl = ''
      this.syncStoryboardGenerationMeta({
        shots: [],
        finalVideoUrl: '',
        clearGeneratedFiles: true,
      })
    },
    updateOutlineEpisode(episode, titleOrFields, summary) {
      const ep = this.outline.find(e => e.episode === episode)
      if (ep) {
        const nextFields = (
          titleOrFields && typeof titleOrFields === 'object'
            ? titleOrFields
            : { title: titleOrFields, summary }
        )
        Object.entries(nextFields).forEach(([key, value]) => {
          if (value !== undefined) ep[key] = value
        })
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
      const storyboardGeneration = hydrateStoryboardGeneration(storyData.meta || {})
      this.setShots(storyboardGeneration.shots)
      this.setStoryboardFinalVideoUrl(storyboardGeneration.finalVideoUrl)
      this.sceneReferenceAssets = hydrateSceneReferenceAssets(storyData.meta || {}, this.scenes)
      this.ensureSceneReferenceAssets()
      this.characterImages = storyData.character_images || {}
      this.setArtStyle(storyData.art_style || '')
      this.wbHistory = storyData.wb_history || []
      this.wbTurn = storyData.wb_turn || 0
      this.step3Done = (storyData.scenes || []).length > 0
      this.setManualPipelineContext({
        projectId: storyboardGeneration.projectId || storyData.id || '',
        pipelineId: storyboardGeneration.pipelineId || '',
        storyId: storyboardGeneration.storyId || storyData.id || '',
      })
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
        this.clearShots()
        this.sceneReferenceAssets = {}
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
