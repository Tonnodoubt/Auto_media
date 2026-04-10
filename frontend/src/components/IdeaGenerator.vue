<template>
  <div class="generator">
    <div class="gen-title">组合灵感生成器</div>
    <div class="gen-note">
      这里选中的故事题材会同步到主流程，并影响后续 AI 改写和世界观构建。
    </div>

    <div class="dimensions">
      <div v-for="dim in dimensions" :key="dim.key" class="dim-block">
        <div class="dim-header">
          <span class="dim-label">{{ dim.label }}</span>
          <button class="dice-btn" @click="randomDim(dim)" title="随机">🎲</button>
        </div>
        <div class="dim-options">
          <button
            v-for="opt in dim.options"
            :key="opt"
            class="dim-opt"
            :class="{ selected: getSelectedValue(dim.key) === opt }"
            @click="select(dim.key, opt)"
          >{{ opt }}</button>
        </div>
        <input
          v-if="dim.key === 'genre' && props.selectedGenreKey === props.customGenreKey"
          :value="props.customGenre"
          class="dim-input"
          type="text"
          placeholder="请输入你想要的题材，例如：民国虐恋、职场黑马、末日求生"
          @input="updateCustomGenre($event.target.value)"
        />
        <div
          v-if="dim.key === 'genre'"
          class="dim-note"
          :class="{ warn: props.selectedGenreKey === props.customGenreKey && !props.customGenre.trim() }"
        >
          {{ props.selectedGenreKey === props.customGenreKey && !props.customGenre.trim()
            ? '选择“其他”后，请补充具体题材。'
            : '题材会继续同步到主流程，作为后续内容约束。' }}
        </div>
      </div>
    </div>

    <div class="gen-actions">
      <button class="random-all-btn" @click="randomAll">🎲 全部随机</button>
      <button class="gen-btn" :disabled="!canGenerate" @click="generate">生成灵感 →</button>
    </div>

    <div v-if="preview" class="preview">{{ preview }}</div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  selectedGenreKey: {
    type: String,
    default: '',
  },
  customGenre: {
    type: String,
    default: '',
  },
  genreOptions: {
    type: Array,
    default: () => [],
  },
  customGenreKey: {
    type: String,
    default: '其他',
  },
})

const emit = defineEmits(['apply', 'update:selectedGenreKey', 'update:customGenre'])

const dimensions = computed(() => [
  {
    key: 'genre',
    label: '故事题材',
    options: props.genreOptions,
  },
  {
    key: 'character',
    label: '人物身份',
    options: ['外卖小哥', '落魄千金', '退役特种兵', '冷酷总裁', '女扮男装刺客', '废柴修仙者', '顶流明星', '孤儿院少年', '法医', '星际佣兵', '御厨', '女帝', '黑客', '流浪歌手', '私家侦探', '豪门继承人', '落魄书生', '神秘杀手', '天才少女', '末世幸存者'],
  },
  {
    key: 'era',
    label: '时代背景',
    options: ['现代都市', '古代架空', '近未来赛博', '末世废土', '修仙界', '星际联邦', '民国乱世', '架空王朝', '蒸汽朋克', '异世大陆', '平行宇宙', '海底文明', '后启示录', '魔法学院'],
  },
  {
    key: 'setting',
    label: '特殊设定',
    options: ['失忆', '穿越', '觉醒异能', '女扮男装', '替身', '卧底', '系统附身', '灵魂互换', '时间循环', '双重身份', '重生复仇', '契约婚姻', '身份互换', '诅咒缠身', '绑定命运', '隐藏血脉'],
  },
  {
    key: 'conflict',
    label: '核心冲突',
    options: ['身份揭穿', '豪门恩怨', '复仇逆袭', '阴谋对抗', '禁忌之恋', '争夺继承权', '生死追杀', '权力游戏', '家族秘密', '背叛与救赎', '夺位之争', '跨越阶级', '组织内斗', '真相追查', '守护与牺牲'],
  },
  {
    key: 'tone',
    label: '情感基调',
    options: ['甜宠', '虐恋', '强爽反击', '治愈温情', '轻松搞笑', '黑色幽默', '紧张压迫', '燃系热血', '细腻慢热', '先虐后甜'],
  },
  {
    key: 'scene',
    label: '关键场景',
    options: ['合租同屋', '假扮恋人', '被迫合作', '流落街头', '卧底潜伏', '逃婚出走', '意外相遇', '重回故地', '绝境求生', '豪门宴会', '荒岛困境', '监狱同牢', '战场重逢', '密室逃脱', '末日避难所', '皇宫深处'],
  },
])

const selected = ref({})
const preview = ref('')

const isGenreValid = computed(() => props.selectedGenreKey !== props.customGenreKey || Boolean(props.customGenre.trim()))
const canGenerate = computed(() => (
  Object.keys(selected.value).length + (props.selectedGenreKey && isGenreValid.value ? 1 : 0)
) >= 3)

function getSelectedValue(key) {
  if (key === 'genre') return props.selectedGenreKey
  return selected.value[key]
}

function updateGenreKey(value) {
  emit('update:selectedGenreKey', value)
  preview.value = ''
}

function updateCustomGenre(value) {
  emit('update:customGenre', value)
  preview.value = ''
}

function pickRandomOption(options = []) {
  if (!Array.isArray(options) || !options.length) return ''
  return options[Math.floor(Math.random() * options.length)] || ''
}

function select(key, opt) {
  if (key === 'genre') {
    const next = props.selectedGenreKey === opt ? '' : opt
    updateGenreKey(next)
    if (next !== props.customGenreKey) {
      updateCustomGenre('')
    }
    return
  }
  selected.value = { ...selected.value, [key]: opt }
  preview.value = ''
}

function randomDim(dim) {
  if (dim.key === 'genre') {
    const available = dim.options.filter(opt => opt !== props.customGenreKey)
    const opt = pickRandomOption(available)
    updateGenreKey(opt)
    updateCustomGenre('')
    return
  }
  const opt = pickRandomOption(dim.options)
  if (!opt) return
  selected.value = { ...selected.value, [dim.key]: opt }
  preview.value = ''
}

function randomAll() {
  const next = {}
  for (const dim of dimensions.value) {
    if (dim.key === 'genre') {
      const available = dim.options.filter(opt => opt !== props.customGenreKey)
      const opt = pickRandomOption(available)
      updateGenreKey(opt)
      updateCustomGenre('')
      continue
    }
    const opt = pickRandomOption(dim.options)
    if (opt) next[dim.key] = opt
  }
  selected.value = next
  preview.value = ''
}

// 把选中的维度组合成一句自然语言灵感
function generate() {
  const s = selected.value
  const leadParts = []
  const detailParts = []
  // Genre is synced from Step1Inspire via props, so selected.value only stores
  // the non-genre dimensions and getSelectedValue('genre') reads from props.

  if (s.character && s.era) {
    leadParts.push(`${s.era}里的${s.character}`)
  } else if (s.character) {
    leadParts.push(`一个${s.character}`)
  } else if (s.era) {
    leadParts.push(`${s.era}背景下`)
  }

  if (s.setting) {
    if (leadParts.length) {
      detailParts.push(`因${s.setting}`)
    } else {
      leadParts.push(`一个因${s.setting}而被卷入命运转折的人`)
    }
  }

  if (s.scene) detailParts.push(`在${s.scene}的情境下`)
  if (s.conflict) detailParts.push(`卷入${s.conflict}`)

  let mainSentence = [...leadParts, ...detailParts].join('，')
  if (mainSentence) {
    mainSentence += '。'
  }

  let closingSentence = ''
  if (s.tone) {
    closingSentence = `故事整体气质偏${s.tone}。`
  }

  const text = `${mainSentence}${closingSentence}`.trim()
  preview.value = text
  emit('apply', text)
}
</script>

<style scoped src="../style/components/ideagenerator.css"></style>
