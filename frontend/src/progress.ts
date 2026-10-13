/** Format project progress at the UI boundary; keep API precision unchanged. */
export function progressPercent(value: unknown): number {
  const percent = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(percent) ? Math.round(Math.max(0, Math.min(100, percent))) : 0;
}
