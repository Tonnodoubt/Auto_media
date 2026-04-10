import { hasCompleteGeneratedScript } from './scriptValidation.js'

function hasStory(store) {
  return !!store?.storyId
}

function hasOutline(store) {
  return !!store?.meta
}

function hasWorldSummary(store) {
  return typeof store?.selectedSetting === 'string' && store.selectedSetting.trim().length > 0
}

function hasScript(store) {
  return hasCompleteGeneratedScript({
    outline: store?.outline,
    scenes: store?.scenes,
  })
}

function isStep2Complete(store) {
  return Number(store?.wbTurn || 0) >= 6 && !store?.wbCurrentQuestion
}

export function canAccessStep(store, step) {
  switch (step) {
    case 1:
      return true
    case 2:
      return hasStory(store)
    case 3:
      return isStep2Complete(store) && hasWorldSummary(store)
    case 4:
    case 5:
      return hasScript(store)
    default:
      return false
  }
}

export function getStepRedirectPath(store, step) {
  if (canAccessStep(store, step)) {
    switch (step) {
      case 1:
        return '/step1'
      case 2:
        return '/step2'
      case 3:
        return '/step3'
      case 4:
        return '/step4'
      case 5:
        return '/video-generation'
      default:
        return '/step1'
    }
  }

  if (!hasStory(store)) return '/step1'
  if (!isStep2Complete(store)) return '/step2'
  if (!hasWorldSummary(store)) return '/step2'
  if (!hasScript(store)) return '/step3'
  return '/step1'
}
