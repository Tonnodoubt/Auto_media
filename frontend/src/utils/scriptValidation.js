function normalizeEpisodeNumber(value) {
  if (value == null) return null
  const normalized = String(value).trim()
  if (!normalized) return null
  const parsed = Number.parseInt(normalized, 10)
  return Number.isInteger(parsed) ? parsed : null
}

export function cloneSerializable(value, fallback = null) {
  try {
    return JSON.parse(JSON.stringify(value))
  } catch {
    return fallback
  }
}

export function getIncompleteScriptEpisodes({ outline = [], scenes = [] } = {}) {
  if (!Array.isArray(outline) || outline.length === 0) return []

  const sceneMap = new Map()
  if (Array.isArray(scenes)) {
    scenes.forEach(episode => {
      if (!episode || typeof episode !== 'object') return
      const episodeNumber = normalizeEpisodeNumber(episode.episode)
      if (episodeNumber == null || sceneMap.has(episodeNumber)) return
      sceneMap.set(episodeNumber, episode)
    })
  }

  const incompleteEpisodes = []
  outline.forEach(episode => {
    if (!episode || typeof episode !== 'object') return
    const episodeNumber = normalizeEpisodeNumber(episode.episode)
    if (episodeNumber == null) return

    const generatedEpisode = sceneMap.get(episodeNumber)
    if (!generatedEpisode || !Array.isArray(generatedEpisode.scenes) || generatedEpisode.scenes.length === 0) {
      incompleteEpisodes.push(episodeNumber)
    }
  })
  return incompleteEpisodes
}

export function hasCompleteGeneratedScript({ outline = [], scenes = [] } = {}) {
  if (!Array.isArray(outline) || outline.length === 0) return false
  return getIncompleteScriptEpisodes({ outline, scenes }).length === 0
}

export function formatEpisodeList(episodes = []) {
  if (!Array.isArray(episodes) || episodes.length === 0) return ''
  return episodes.map(episode => `第 ${episode} 集`).join('、')
}
