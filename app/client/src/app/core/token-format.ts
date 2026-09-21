export const formatCompactTokenCount = (
  value: number | null | undefined,
): string => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    return 'Unavailable';
  }
  if (value >= 1_000_000) {
    const decimals = value < 100_000_000 ? 2 : 0;
    return `${trimTrailingZeroes((value / 1_000_000).toFixed(decimals))}M`;
  }
  if (value >= 1_000) {
    const decimals = value < 100_000 ? 2 : 0;
    return `${trimTrailingZeroes((value / 1_000).toFixed(decimals))}K`;
  }
  return Math.round(value).toLocaleString();
};

const trimTrailingZeroes = (value: string): string => {
  if (!value.includes('.')) {
    return value;
  }
  return value.replace(/0+$/u, '').replace(/\.$/u, '');
};
