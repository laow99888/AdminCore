export const DEFAULT_PRIMARY_COLOR = '#14B8A6'
export const PRIMARY_STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950] as const

export function normalizeThemeColor(value: unknown): string | null {
  return typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value) ? value.toUpperCase() : null
}

function channels(hex: string): number[] {
  return [1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16))
}

export function mixThemeColor(color: string, other: string, amount: number): string {
  const target = channels(other)
  return '#' + channels(color).map((channel, index) => Math.round(channel + (target[index]! - channel) * amount).toString(16).padStart(2, '0')).join('').toUpperCase()
}

export function colorContrast(first: string, second: string): number {
  const luminance = (color: string) => channels(color).map(channel => {
    const value = channel / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  }).reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index]!, 0)
  const values = [luminance(first), luminance(second)].sort((a, b) => b - a)
  return (values[0]! + 0.05) / (values[1]! + 0.05)
}

/** Preserve the selected hue where possible; extreme colors map to a readable shade. */
export function createThemePalette(seed: string, dark: boolean) {
  const normalized = normalizeThemeColor(seed)
  if (!normalized) throw new TypeError('Invalid theme color')
  const surface = dark ? '#1E293B' : '#FFFFFF'
  const onColor = dark ? '#000000' : '#FFFFFF'
  let primary = normalized
  for (let percent = 0; percent <= 100; percent++) {
    primary = mixThemeColor(normalized, dark ? '#FFFFFF' : '#000000', percent / 100)
    if (colorContrast(primary, surface) >= 5.2 && colorContrast(primary, onColor) >= 5.2) break
  }
  const palette: Record<number, string> = {
    50: mixThemeColor(primary, '#FFFFFF', 0.96),
    100: mixThemeColor(primary, '#FFFFFF', 0.90),
    200: mixThemeColor(primary, '#FFFFFF', 0.76),
    300: mixThemeColor(primary, '#FFFFFF', 0.55),
    400: mixThemeColor(primary, '#FFFFFF', 0.25),
    500: primary,
    600: mixThemeColor(primary, '#000000', dark ? 0.03 : 0.10),
    700: mixThemeColor(primary, '#000000', dark ? 0.06 : 0.20),
    800: mixThemeColor(primary, '#000000', 0.70),
    900: mixThemeColor(primary, '#000000', 0.84),
    950: mixThemeColor(primary, '#000000', 0.92),
  }
  const hover = dark ? palette[400]! : palette[600]!
  const active = dark ? primary : palette[700]!
  const subtle = dark ? palette[900]! : palette[50]!
  return { palette, primary, onColor, hover, active, subtle }
}
