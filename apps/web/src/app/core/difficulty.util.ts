export type DifficultyLabel =
  | 'very_easy'
  | 'easy'
  | 'neutral'
  | 'hard'
  | 'very_hard';

export const DIFFICULTY_DISPLAY: Record<DifficultyLabel, string> = {
  very_easy: 'Very easy',
  easy: 'Easy',
  neutral: 'Neutral',
  hard: 'Hard',
  very_hard: 'Very hard',
};

export const FDR_LEGEND: { level: number; label: string }[] = [
  { level: 1, label: 'Very easy' },
  { level: 2, label: 'Easy' },
  { level: 3, label: 'Neutral' },
  { level: 4, label: 'Hard' },
  { level: 5, label: 'Very hard' },
];

const LABEL_ORDER: DifficultyLabel[] = [
  'very_easy',
  'easy',
  'neutral',
  'hard',
  'very_hard',
];

/** Clamp and round to FDR level 1–5. */
export function clampDifficultyLevel(value: number): number {
  return Math.min(5, Math.max(1, Math.round(value)));
}

export function difficultyClass(level: number): string {
  return `diff-pill diff-${clampDifficultyLevel(level)}`;
}

export function overallDifficultyClass(averageScore: number): string {
  return `diff-pill diff-${clampDifficultyLevel(averageScore)}`;
}

export function difficultyLabel(level: number, apiLabel?: string): string {
  if (apiLabel && apiLabel in DIFFICULTY_DISPLAY) {
    return DIFFICULTY_DISPLAY[apiLabel as DifficultyLabel];
  }
  return DIFFICULTY_DISPLAY[LABEL_ORDER[clampDifficultyLevel(level) - 1]];
}

export function overallDifficultyLabel(averageScore: number, apiLabel?: string): string {
  return difficultyLabel(averageScore, apiLabel);
}

/** Same 1–5 pill colours as FDR; tier 1 (green) = strongest outlook, 5 (red) = weakest. */
export const OPPORTUNITY_LEGEND: { level: number; label: string }[] = [
  { level: 1, label: 'Strong' },
  { level: 2, label: 'Good' },
  { level: 3, label: 'Moderate' },
  { level: 4, label: 'Weak' },
  { level: 5, label: 'Poor' },
];

const CS_PERCENT_BREAKS = [18, 24, 30, 36] as const;
const GOALS_PERCENT_BREAKS = [54, 62, 70, 78] as const;

export function opportunityTier(percent: number, kind: 'cs' | 'goals'): number {
  const breaks = kind === 'cs' ? CS_PERCENT_BREAKS : GOALS_PERCENT_BREAKS;
  if (percent >= breaks[3]) {
    return 1;
  }
  if (percent >= breaks[2]) {
    return 2;
  }
  if (percent >= breaks[1]) {
    return 3;
  }
  if (percent >= breaks[0]) {
    return 4;
  }
  return 5;
}

export function opportunityPillClass(percent: number, kind: 'cs' | 'goals'): string {
  return difficultyClass(opportunityTier(percent, kind));
}
