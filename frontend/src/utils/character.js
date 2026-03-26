export function getCharacterKey(character = {}) {
  const raw = character?.id != null && String(character.id).trim()
    ? String(character.id)
    : character?.name
  const normalized = String(raw || '')
    .normalize('NFKC')
    .trim()
    .replace(/\s+/g, ' ')
    .toLowerCase()
  return normalized || ''
}

export function matchesCharacter(candidate = {}, target = {}) {
  const targetId = String(target?.id || '').trim()
  return !!targetId && String(candidate?.id || '').trim() === targetId
}

export function findCharacterByRef(characters = [], target = {}) {
  return characters.find(character => matchesCharacter(character, target)) || null
}

export function findCharacterImageEntry(characterImages = {}, character = {}) {
  const key = String(character?.id || '').trim()
  if (key && characterImages[key]) {
    return characterImages[key]
  }
  const legacyNameKey = String(character?.name || '').trim()
  if (legacyNameKey && characterImages[legacyNameKey]) {
    return characterImages[legacyNameKey]
  }
  for (const candidate of Object.values(characterImages || {})) {
    if (!candidate || typeof candidate !== 'object') continue
    if (key && String(candidate.character_id || '').trim() === key) {
      return candidate
    }
    if (legacyNameKey && String(candidate.character_name || '').trim() === legacyNameKey) {
      return candidate
    }
  }
  return null
}
