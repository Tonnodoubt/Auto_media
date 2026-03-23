import { useSettingsStore } from '../stores/settings.js'

/**
 * 统一 Header 构建：
 * - LLM 相关：优先使用文本生成专用 Key，回退到默认 LLM Key
 * - 图片/视频：优先使用专用 Key，回退到默认 Key
 */
function getHeaders() {
  const settings = useSettingsStore()
  const headers = { 'Content-Type': 'application/json' }
  if (!settings.useMock) {
    if (settings.effectiveLlmApiKey)   headers['X-LLM-API-Key']    = settings.effectiveLlmApiKey
    if (settings.effectiveLlmBaseUrl)  headers['X-LLM-Base-URL']   = settings.effectiveLlmBaseUrl
    if (settings.effectiveLlmProvider) headers['X-LLM-Provider']   = settings.effectiveLlmProvider
    if (settings.effectiveLlmModel)    headers['X-LLM-Model']      = settings.effectiveLlmModel
  }
  if (settings.effectiveImageApiKey)  headers['X-Image-API-Key']  = settings.effectiveImageApiKey
  if (settings.effectiveImageBaseUrl) headers['X-Image-Base-URL'] = settings.effectiveImageBaseUrl
  if (settings.effectiveVideoProvider) headers['X-Video-Provider'] = settings.effectiveVideoProvider
  if (settings.effectiveVideoApiKey)  headers['X-Video-API-Key']  = settings.effectiveVideoApiKey
  if (settings.effectiveVideoBaseUrl) headers['X-Video-Base-URL'] = settings.effectiveVideoBaseUrl
  return headers
}

function getUrl(path) {
  const settings = useSettingsStore()
  const base = settings.backendUrl ? settings.backendUrl.replace(/\/$/, '') : ''
  return `${base}/api/v1/story${path}`
}

function getPipelineUrl(path) {
  const settings = useSettingsStore()
  const base = settings.backendUrl ? settings.backendUrl.replace(/\/$/, '') : ''
  return `${base}/api/v1/pipeline${path}`
}

export async function deleteStory(storyId) {
  const res = await fetch(getUrl(`/${storyId}`), { method: 'DELETE', headers: getHeaders() })
  if (!res.ok) throw new Error(`请求失败 (${res.status})`)
  return res.json()
}

export async function listStories() {
  const res = await fetch(getUrl('/'), { headers: getHeaders() })
  if (!res.ok) throw new Error(`请求失败 (${res.status})`)
  return res.json()
}

export async function getStory(storyId) {
  const res = await fetch(getUrl(`/${storyId}`), { headers: getHeaders() })
  if (!res.ok) throw new Error(`请求失败 (${res.status})`)
  return res.json()
}

export async function finalizeScript(storyId) {
  const res = await fetch(getUrl(`/${storyId}/finalize`), { method: 'POST', headers: getHeaders() })
  if (!res.ok) throw new Error(`请求失败 (${res.status})`)
  return res.json()
}

export async function startStoryboard(storyId, script, provider) {
  const res = await fetch(getPipelineUrl(`/${storyId}/storyboard`), {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ script, provider }),
  })
  if (!res.ok) throw new Error(`请求失败 (${res.status})`)
  return res.json()
}

export async function getPipelineStatus(storyId) {
  const res = await fetch(getPipelineUrl(`/${storyId}/status`), { headers: getHeaders() })
  if (!res.ok) throw new Error(`请求失败 (${res.status})`)
  return res.json()
}

export async function analyzeIdea(idea, genre, tone) {
  const res = await fetch(getUrl('/analyze-idea'), {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ idea, genre, tone }),
  })
  if (!res.ok) throw new Error(`请求失败 (${res.status})`)
  return res.json()
}

export async function worldBuildingStart(idea) {
  const res = await fetch(getUrl('/world-building/start'), {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ idea }),
  })
  if (!res.ok) throw new Error(`请求失败 (${res.status})`)
  return res.json()
}

export async function worldBuildingTurn(storyId, answer) {
  const res = await fetch(getUrl('/world-building/turn'), {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ story_id: storyId, answer }),
  })
  if (!res.ok) throw new Error(`请求失败 (${res.status})`)
  return res.json()
}

export async function generateOutline(storyId, selectedSetting) {
  const res = await fetch(getUrl('/generate-outline'), {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ story_id: storyId, selected_setting: selectedSetting }),
  })
  if (!res.ok) throw new Error(`请求失败 (${res.status})`)
  return res.json()
}

export async function refineStory(storyId, changeType, changeSummary) {
  const res = await fetch(getUrl('/refine'), {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ story_id: storyId, change_type: changeType, change_summary: changeSummary }),
  })
  if (!res.ok) return null
  return res.json()
}

export async function patchStory(storyId, fields) {
  const res = await fetch(getUrl('/patch'), {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ story_id: storyId, ...fields }),
  })
  if (!res.ok) return null
  return res.json()
}

export async function applyChatChanges(storyId, changeType, chatHistory, currentItem, allCharacters, allOutline) {
  const res = await fetch(getUrl('/apply-chat'), {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({
      story_id: storyId,
      change_type: changeType,
      chat_history: chatHistory,
      current_item: currentItem,
      all_characters: allCharacters ?? null,
      all_outline: allOutline ?? null,
    }),
  })
  if (!res.ok) return null
  return res.json()
}

export async function streamChat(storyId, message, onChunk, onDone, onError, signal) {
  let res
  try {
    res = await fetch(getUrl('/chat'), {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ story_id: storyId, message }),
      signal,
    })
  } catch (e) {
    if (e.name === 'AbortError') return
    onError?.(e.message); return
  }
  if (!res.ok) { onError?.(`请求失败 (${res.status})`); return }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (signal?.aborted) { reader.cancel(); return }
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6)
        if (payload === '[DONE]') { onDone(); return }
        if (payload.startsWith('[ERROR]')) { onError?.(payload.slice(8)); return }
        onChunk(payload)
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') return
    onError?.(e.message); return
  }
  onDone()
}

export async function streamScript(storyId, onScene, onDone, onError, signal) {
  let res
  try {
    res = await fetch(getUrl('/generate-script'), {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ story_id: storyId }),
      signal,
    })
  } catch (e) {
    if (e.name === 'AbortError') return
    onError?.(e.message); return
  }
  if (!res.ok) { onError?.(`请求失败 (${res.status})`); return }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (signal?.aborted) { reader.cancel(); return }
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6).trim()
        if (payload === '[DONE]') { onDone(); return }
        if (payload.startsWith('[ERROR]')) { onError?.(payload.slice(8).trim()); return }
        try { onScene(JSON.parse(payload)) } catch { onError?.('数据解析失败'); return }
      }
    }
    if (buffer.startsWith('data: ')) {
      const payload = buffer.slice(6).trim()
      if (payload && payload !== '[DONE]') {
        try { onScene(JSON.parse(payload)) } catch {}
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') return
    onError?.(e.message); return
  }
  onDone()
}

// Character design image API
function getCharacterUrl(path) {
  const settings = useSettingsStore()
  const base = settings.backendUrl ? settings.backendUrl.replace(/\/$/, '') : ''
  return `${base}/api/v1/character${path}`
}

export async function generateCharacterImage(storyId, character) {
  const settings = useSettingsStore()
  const res = await fetch(getCharacterUrl('/generate'), {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({
      story_id: storyId,
      character_name: character.name,
      role: character.role || '',
      description: character.description || '',
      ...(settings.effectiveImageModel ? { model: settings.effectiveImageModel } : {}),
    }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw new Error(data?.detail || `请求失败 (${res.status})`)
  }
  return res.json()
}

export async function generateAllCharacterImages(storyId, characters) {
  const settings = useSettingsStore()
  const res = await fetch(getCharacterUrl('/generate-all'), {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({
      story_id: storyId,
      characters: characters,
      ...(settings.effectiveImageModel ? { model: settings.effectiveImageModel } : {}),
    }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw new Error(data?.detail || `请求失败 (${res.status})`)
  }
  return res.json()
}

export async function getCharacterImages(storyId) {
  const res = await fetch(getCharacterUrl(`/${storyId}/images`), { headers: getHeaders() })
  if (!res.ok) throw new Error(`请求失败 (${res.status})`)
  return res.json()
}
