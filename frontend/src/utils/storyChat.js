export function normalizeChatText(text) {
  if (!text) return ''

  const lines = String(text)
    .replace(/\r/g, '')
    .split('\n')
    .map(line => line.trim())

  const compact = []
  for (const line of lines) {
    if (!line) {
      if (compact.length > 0 && compact[compact.length - 1] !== '') {
        compact.push('')
      }
      continue
    }
    compact.push(line)
  }

  while (compact.length > 0 && compact[compact.length - 1] === '') {
    compact.pop()
  }

  return compact.join('\n')
}

export function stripRefineMarker(text) {
  return normalizeChatText(String(text || '').replace(/\n?REFINE_JSON:[^\n]*/g, ''))
}

export function extractRefinePayload(text) {
  const rawText = String(text || '')
  const match = rawText.match(/REFINE_JSON:([^\n]+)/)
  let refine = null

  if (match) {
    try {
      refine = JSON.parse(match[1].trim())
    } catch {
      refine = null
    }
  }

  return {
    displayText: stripRefineMarker(rawText),
    refine,
  }
}

function normalizeCharacterChatLabels(text) {
  return normalizeChatText(
    String(text || '')
      .replace(/当前角色修改\s*[:：]/g, '当前角色修改：')
      .replace(/对剧情的影响\s*[:：]/g, '对剧情的影响：')
  )
}

function splitSectionItems(text) {
  const items = String(text || '')
    .split(/[；;]+/)
    .flatMap(item => item.replace(/\s+(?=\d+[.)．]\s*)/g, '\n').split('\n'))
    .map(item => item.replace(/^[、\-•\d.)．\s]+/, '').trim())
    .filter(Boolean)

  return [...new Set(items)]
}

function isDefaultStoryImpactItem(item) {
  const normalized = String(item || '').trim().replace(/[。！!？?；;]+$/g, '')
  return normalized === '基本不影响主线，仅补强人物一致性' || normalized === '基本不影响主线，仅同步补强人物一致性'
}

function isStoryImpactItem(item) {
  return /剧情|主线|冲突|后续|联动|影响|第\s*\d+\s*集|故事|情节|反转|结局/.test(String(item || ''))
}

function isCharacterChangeItem(item) {
  return /修改|强化|调整|补充/.test(String(item || ''))
}

function pushUniqueItems(target, items) {
  for (const item of items) {
    const normalized = String(item || '').trim()
    if (!normalized || target.includes(normalized)) continue
    target.push(normalized)
  }
}

function extractLabeledSection(text, label, nextLabels = []) {
  const normalized = normalizeCharacterChatLabels(text)
  const start = normalized.indexOf(label)
  if (start === -1) return ''

  const contentStart = start + label.length
  let contentEnd = normalized.length

  for (const nextLabel of nextLabels) {
    const nextIndex = normalized.indexOf(nextLabel, contentStart)
    if (nextIndex !== -1 && nextIndex < contentEnd) {
      contentEnd = nextIndex
    }
  }

  return normalized.slice(contentStart, contentEnd).trim()
}

export function parseCharacterChatSections(text) {
  const normalized = normalizeCharacterChatLabels(text)
  const lines = normalized.split('\n').map(line => line.trim()).filter(Boolean)
  const sections = []
  let characterChanges = []
  let storyImpact = []

  const labeledCharacterChanges = extractLabeledSection(
    normalized,
    '当前角色修改：',
    ['对剧情的影响：']
  )
  const labeledStoryImpact = extractLabeledSection(
    normalized,
    '对剧情的影响：',
    []
  )

  if (labeledCharacterChanges) {
    pushUniqueItems(
      characterChanges,
      splitSectionItems(labeledCharacterChanges).filter(item => !isDefaultStoryImpactItem(item))
    )
  }
  if (labeledStoryImpact) {
    pushUniqueItems(storyImpact, splitSectionItems(labeledStoryImpact))
  }

  for (const line of lines) {
    if (line.startsWith('当前角色修改：')) {
      const inlineImpactIndex = line.indexOf('对剧情的影响：')
      if (inlineImpactIndex !== -1) {
        const currentText = line.slice('当前角色修改：'.length, inlineImpactIndex)
        const impactText = line.slice(inlineImpactIndex + '对剧情的影响：'.length)
        pushUniqueItems(
          characterChanges,
          splitSectionItems(currentText).filter(item => !isDefaultStoryImpactItem(item))
        )
        pushUniqueItems(storyImpact, splitSectionItems(impactText))
        continue
      }
      pushUniqueItems(
        characterChanges,
        splitSectionItems(line.slice('当前角色修改：'.length)).filter(item => !isDefaultStoryImpactItem(item))
      )
      continue
    }
    if (line.startsWith('对剧情的影响：')) {
      pushUniqueItems(storyImpact, splitSectionItems(line.slice('对剧情的影响：'.length)))
      continue
    }

    const looseItems = splitSectionItems(line)
    let handledLooseItems = false

    for (const item of looseItems) {
      const hasCharacterChangeContext = isCharacterChangeItem(item)
      const hasStoryImpactContext = isStoryImpactItem(item)

      if (hasStoryImpactContext) {
        pushUniqueItems(storyImpact, [item])
        handledLooseItems = true
        continue
      }

      if (hasCharacterChangeContext) {
        pushUniqueItems(characterChanges, [item])
        handledLooseItems = true
      }
    }

    if (handledLooseItems) {
      continue
    }
  }

  const normalizedCharacterChanges = []
  const normalizedStoryImpact = [...storyImpact]

  for (const item of characterChanges) {
    if (isStoryImpactItem(item)) {
      pushUniqueItems(normalizedStoryImpact, [item.replace(/^对剧情的影响：/, '').trim()])
      continue
    }
    pushUniqueItems(normalizedCharacterChanges, [item.replace(/^当前角色修改：/, '').trim()])
  }

  if (normalizedCharacterChanges.length) {
    sections.push({
      key: 'character_changes',
      title: '当前角色修改',
      items: normalizedCharacterChanges,
    })
  }

  const storyImpactItems = normalizedStoryImpact.filter(item => !isDefaultStoryImpactItem(item))
  if (storyImpactItems.length) {
    sections.push({
      key: 'story_impact',
      title: '对剧情的影响',
      items: storyImpactItems,
    })
  }

  return sections
}
