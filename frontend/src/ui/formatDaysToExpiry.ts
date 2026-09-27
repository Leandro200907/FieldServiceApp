export function formatDaysToExpiry(days: number): string {
  const absoluteDays = Math.abs(days);
  const unit = absoluteDays === 1 ? 'día' : 'días';
  return days >= 0 ? `vence en ${absoluteDays} ${unit}` : `venció hace ${absoluteDays} ${unit}`;
}

