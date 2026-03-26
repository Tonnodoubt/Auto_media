import test from 'node:test'
import assert from 'node:assert/strict'

import { parseCharacterChatSections } from './storyChat.js'
import { getSectionItems } from './storyChat.test-helpers.js'

test('keeps multiline story impact content when there is no next label', () => {
  const sections = parseCharacterChatSections('对剧情的影响：第一条\n第二条')

  assert.deepEqual(getSectionItems(sections, 'story_impact'), ['第一条', '第二条'])
})
