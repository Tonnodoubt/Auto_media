import test from 'node:test'
import assert from 'node:assert/strict'

import { parseCharacterChatSections } from './storyChat.js'
import { getSectionItems } from './storyChat.test-helpers.js'

test('strips numbered prefixes that use closing parenthesis or fullwidth dot', () => {
  const sections = parseCharacterChatSections('1) 修改角色技能 2． 剧情冲突提前爆发')

  assert.deepEqual(getSectionItems(sections, 'character_changes'), ['修改角色技能'])
  assert.deepEqual(getSectionItems(sections, 'story_impact'), ['剧情冲突提前爆发'])
})
