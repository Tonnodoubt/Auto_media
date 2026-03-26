export const ART_STYLE_PRESETS = [
  { id: 'anime', name: '日系动漫', icon: '🌸', prompt: '日系动漫风格，细腻线条，鲜艳色彩，二次元，高质量动漫插画' },
  { id: 'realistic', name: '写实摄影', icon: '📷', prompt: '写实摄影风格，电影级画质，自然光影，高清细节，真实质感' },
  { id: 'ink', name: '古风水墨', icon: '🖌️', prompt: '中国传统水墨画风格，淡雅笔墨，古典意境，飘逸仙气，古风人物' },
  { id: 'cyberpunk', name: '赛博朋克', icon: '🌃', prompt: '赛博朋克风格，霓虹光效，未来都市，蓝紫色调，机械感' },
  { id: 'oil', name: '油画风格', icon: '🖼️', prompt: '欧式油画风格，厚重笔触，古典光影，文艺复兴质感，浓郁色彩' },
  { id: 'illustration', name: '清新插画', icon: '🌿', prompt: '清新治愈插画风格，柔和配色，简洁线条，扁平化，温馨可爱' },
  { id: 'gothic', name: '暗黑哥特', icon: '🦇', prompt: '暗黑哥特风格，深沉暗调，神秘阴郁，黑红配色，奇幻美学' },
  { id: 'pixel', name: '像素艺术', icon: '👾', prompt: '像素艺术风格，复古8-bit游戏美学，像素点阵，鲜明对比色' },
  { id: 'sketch', name: '简笔线稿', icon: '✏️', prompt: '简笔画线稿风格，黑白线条，极简轮廓，手绘感，清晰流畅的单线描边，无填充或淡灰填充' },
]

export const DEFAULT_ART_STYLE_PRESET = ART_STYLE_PRESETS.find(({ id }) => id === 'realistic') || ART_STYLE_PRESETS[0]
export const DEFAULT_ART_STYLE_PROMPT = DEFAULT_ART_STYLE_PRESET.prompt

export const ART_STYLE_PROMPT_TO_LABEL = new Map(
  ART_STYLE_PRESETS.map(({ prompt, name }) => [prompt, name]),
)

export const ART_STYLE_TRUNCATE_LEN = 8
