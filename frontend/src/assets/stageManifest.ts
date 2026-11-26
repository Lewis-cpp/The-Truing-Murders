// Backdrops per stage. Until the art lands (plan week 3) every stage is a CSS
// gradient; the art will be layered on top of these, so they stay as the fallback.
const backdrops: Record<string, string> = {
  // Rainy institute at night, one amber emergency light high up.
  cover:
    'radial-gradient(ellipse 40% 30% at 70% 12%, rgb(212 154 69 / 28%), transparent 70%), linear-gradient(180deg, #1a2230 0%, #0f1319 75%)',
  // Room light sits on the right: the survey card covers the left of the stage.
  // S01 archive room: warm brown walls, a desk lamp.
  S01: 'radial-gradient(ellipse 45% 55% at 80% 40%, rgb(212 154 69 / 45%), transparent 70%), linear-gradient(160deg, #2b2118 0%, #120f0c 85%)',
  // S02 reference room: grey-green, the copier's standby light.
  S02: 'radial-gradient(ellipse 40% 45% at 82% 65%, rgb(110 190 140 / 38%), transparent 70%), linear-gradient(170deg, #1e2622 0%, #0d110f 85%)',
  // S03 data room: cold blue, rows of rack lights.
  S03: 'repeating-linear-gradient(90deg, rgb(90 150 230 / 14%) 0 3px, transparent 3px 56px), radial-gradient(ellipse 45% 60% at 80% 50%, rgb(70 130 220 / 35%), transparent 70%), linear-gradient(180deg, #13203a 0%, #0a0f1a 85%)',
  // S04 power room: dark red, alarm glow over the panel and an amber work light.
  S04: 'radial-gradient(ellipse 40% 45% at 78% 30%, rgb(201 74 56 / 45%), transparent 70%), radial-gradient(ellipse 35% 35% at 88% 80%, rgb(212 154 69 / 30%), transparent 70%), linear-gradient(180deg, #2a1716 0%, #110b0b 85%)',
  // Interrogation and accusation: a single top light over the table.
  interrogation:
    'radial-gradient(ellipse 30% 55% at 50% 0%, rgb(236 232 223 / 22%), transparent 75%), linear-gradient(180deg, #141a24 0%, #0b0e13 90%)',
}

export function backdropFor(key: string): string {
  return backdrops[key] ?? backdrops.cover
}
