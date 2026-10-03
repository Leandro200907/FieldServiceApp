export function formatDaysToExpiry(days: number | null | undefined): string {
  if (days === null || days === undefined) return 'sin fecha de vencimiento';
  const absoluteDays = Math.abs(days);
  const unit = absoluteDays === 1 ? 'día' : 'días';
  return days >= 0 ? `vence en ${absoluteDays} ${unit}` : `venció hace ${absoluteDays} ${unit}`;
}

