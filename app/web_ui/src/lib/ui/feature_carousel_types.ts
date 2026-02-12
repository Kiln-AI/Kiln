export type CarouselFeature = {
  name: string
  subtitle?: string
  description: string
  tooltip?: string
  metrics?: Record<string, number>
  on_click: () => void
}
