import test from 'node:test'
import assert from 'node:assert/strict'

import { parseCharacterChatSections } from './storyChat.js'

function getSectionItems(sections, key) {
  return sections.find(section => section.key === key)?.items || []
}

test('classifies story-first overlap like 剧情修改 into story impact only', () => {
  const sections = parseCharacterChatSections('剧情修改')

  assert.deepEqual(getSectionItems(sections, 'character_changes'), [])
  assert.deepEqual(getSectionItems(sections, 'story_impact'), ['剧情修改'])
})

test('classifies 修改角色技能 as character change even when story items already exist', () => {
  const sections = parseCharacterChatSections(
    '对剧情的影响：第2集冲突提前爆发\n修改角色技能'
  )

  assert.deepEqual(getSectionItems(sections, 'character_changes'), ['修改角色技能'])
  assert.deepEqual(getSectionItems(sections, 'story_impact'), ['第2集冲突提前爆发'])
})

test('splits malformed numbered output and routes each item to the right section', () => {
  const sections = parseCharacterChatSections('1. 修改角色技能 2. 剧情冲突提前爆发')

  assert.deepEqual(getSectionItems(sections, 'character_changes'), ['修改角色技能'])
  assert.deepEqual(getSectionItems(sections, 'story_impact'), ['剧情冲突提前爆发'])
})

test('dedupes repeated items while preserving both character and story sections', () => {
  const sections = parseCharacterChatSections(
    '当前角色修改：强化刀法；强化刀法\n对剧情的影响：第3集提前摊牌；第3集提前摊牌\n强化刀法；剧情反转提前'
  )

  assert.deepEqual(getSectionItems(sections, 'character_changes'), ['强化刀法'])
  assert.deepEqual(getSectionItems(sections, 'story_impact'), ['第3集提前摊牌', '剧情反转提前'])
})
