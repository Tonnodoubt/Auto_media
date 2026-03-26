export function getSectionItems(sections, key) {
  return sections.find(section => section.key === key)?.items || []
}
