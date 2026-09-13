export interface Song {
  id: number;
  key?: string;
  title: string;
  subtitle?: string;
  artist: string;
  charter: string;
  cover?: string;
  description?: string;
  downloads?: number;
  tags?: string[];
  dlc?: { title: string };
  local?: boolean;
  missing?: boolean;
  [key: string]: unknown;
}
export interface Status {
  path: string;
  candidates: string[];
  songs: Song[];
  error: string;
  job: { state: string; message: string; bytes?: number; id?: number };
}
export interface Filters {
  difficulty: string;
  minimum: number;
  maximum: number;
  sort: string;
}
export const defaults: Filters = { difficulty: 'all', minimum: 0, maximum: 99, sort: 'recommended' };
export const tiers = [
  ['Easy', 'easy', 'hasEasyDifficulty', 'easyDifficulty'],
  ['Normal', 'normal', 'hasNormalDifficulty', 'normalDifficulty'],
  ['Hard', 'hard', 'hasHardDifficulty', 'hardDifficulty'],
  ['Extreme', 'extreme', 'hasExtremeDifficulty', 'expertDifficulty'],
  ['XD', 'xd', 'hasXDDifficulty', 'XDDifficulty'],
];
export const collections = [
  { data: 'new', label: 'Newest' },
  { data: 'updated', label: 'Recently updated' },
  { data: 'hotThisWeek', label: 'Top · This week' },
  { data: 'hotThisMonth', label: 'Top · This month' },
  { data: 'topYear', label: 'Top · This year' },
  { data: 'topAllTime', label: 'Top · All time' },
];
export const orders = [
  { data: 'recommended', label: 'Collection order' },
  { data: 'difficultyAsc', label: 'Difficulty · Low to high' },
  { data: 'difficultyDesc', label: 'Difficulty · High to low' },
  { data: 'downloads', label: 'Most downloaded' },
  { data: 'title', label: 'Title · A–Z' },
];
export function difficultyText(song: Song): string {
  return tiers.filter(([, , flag]) => song[flag])
    .map(([label, , , field]) => `${label} ${song[field] ?? '—'}`).join(' · ');
}
export function filterSummary(filters: Filters): string {
  const tier = tiers.find(([, key]) => key === filters.difficulty)?.[0] ?? 'All difficulties';
  return `${tier} · ${filters.minimum}–${filters.maximum}`;
}
