import { OverlayLegend, OverlayLegendEntry } from '../core/types';

export const LEGEND_GRADIENT_MAX_STOPS = 32;
export const LEGEND_TICK_COUNT = 5;
export const HOVER_READOUT_DELAY_MS = 150;

export interface LegendTick {
  /** Position along the colour bar, 0-100. */
  position: number;
  label: string;
}

export interface HoverReadoutValue {
  kind: OverlayLegend['kind'];
  value: number | null;
  label: string;
  units: string | null;
}

const valuedEntries = (entries: readonly OverlayLegendEntry[]): Array<OverlayLegendEntry & { value: number }> => (
  entries
    .filter((entry): entry is OverlayLegendEntry & { value: number } => Number.isFinite(entry.value))
    .sort((left, right) => left.value - right.value)
);

const trimNumber = (value: number, digits: number): string => String(Number(value.toFixed(digits)));

/** Compact legend number: about four significant digits, no trailing zeros. */
export const formatLegendValue = (value: number): string => {
  const magnitude = Math.abs(value);
  if (magnitude >= 1000) return String(Math.round(value));
  if (magnitude >= 100) return trimNumber(value, 1);
  if (magnitude >= 1) return trimNumber(value, 2);
  if (magnitude === 0) return '0';
  return String(Number(value.toPrecision(2)));
};

/** CSS gradient for a continuous legend, downsampled to at most `maxStops` stops placed by value. */
export const legendGradient = (
  entries: readonly OverlayLegendEntry[],
  maxStops = LEGEND_GRADIENT_MAX_STOPS,
): string => {
  const sorted = valuedEntries(entries);
  if (!sorted.length) return '';
  if (sorted.length === 1) return `linear-gradient(to right, ${sorted[0].color}, ${sorted[0].color})`;
  const min = sorted[0].value;
  const span = sorted[sorted.length - 1].value - min || 1;
  const count = Math.max(2, Math.min(maxStops, sorted.length));
  const picks = count === sorted.length
    ? sorted
    : Array.from({ length: count }, (_, index) => sorted[Math.round((index * (sorted.length - 1)) / (count - 1))]);
  const stops = picks.map((entry) => `${entry.color} ${trimNumber(((entry.value - min) / span) * 100, 1)}%`);
  return `linear-gradient(to right, ${stops.join(', ')})`;
};

/** Nearest 1/2/2.5/5 x 10^n step to `raw`. */
const niceStep = (raw: number): number => {
  const power = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / power;
  const factor = fraction < 1.5 ? 1 : fraction < 2.25 ? 2 : fraction < 3.5 ? 2.5 : fraction < 7.5 ? 5 : 10;
  return factor * power;
};

/** About `count` round-valued ticks placed by value; units are appended to the last tick. */
export const legendTicks = (
  entries: readonly OverlayLegendEntry[],
  units: string | null,
  count = LEGEND_TICK_COUNT,
): LegendTick[] => {
  const sorted = valuedEntries(entries);
  if (!sorted.length) return [];
  const min = sorted[0].value;
  const max = sorted[sorted.length - 1].value;
  const suffix = units ? ` ${units}` : '';
  if (min === max || count < 2) return [{ position: 0, label: `${formatLegendValue(min)}${suffix}` }];
  const step = niceStep((max - min) / (count - 1));
  const values: number[] = [];
  for (let value = Math.ceil(min / step - 1e-9) * step; value <= max + step * 1e-9; value += step) {
    values.push(Number(value.toPrecision(12)));
  }
  if (values.length < 2) values.splice(0, values.length, min, max);
  return values.map((value, index) => ({
    position: Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100)),
    label: `${formatLegendValue(value)}${index === values.length - 1 ? suffix : ''}`,
  }));
};

/** One-line readout, e.g. "≈ 301.5 K · 41.90, 12.49"; "—" marks nodata. */
export const formatHoverReadout = (sample: HoverReadoutValue | null, lng: number, lat: number): string => {
  const coordinates = `${lat.toFixed(2)}, ${lng.toFixed(2)}`;
  if (!sample) return `— · ${coordinates}`;
  if (sample.kind === 'continuous' && sample.value !== null) {
    return `≈ ${formatLegendValue(sample.value)}${sample.units ? ` ${sample.units}` : ''} · ${coordinates}`;
  }
  return `${sample.label || '—'} · ${coordinates}`;
};

/** Cache key that collapses positions inside one Web Mercator pixel of a 256 px tile at `z`. */
export const sampleCacheKey = (
  capabilityId: string,
  z: number,
  lng: number,
  lat: number,
  time: string | null | undefined,
): string => {
  const scale = 256 * 2 ** z;
  const sin = Math.min(0.9999, Math.max(-0.9999, Math.sin((lat * Math.PI) / 180)));
  const x = Math.floor(((lng + 180) / 360) * scale);
  const y = Math.floor((0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale);
  return `${capabilityId}|${z}|${x}|${y}|${time || ''}`;
};

/**
 * Debounces hover sampling until the pointer rests. Any movement cancels the
 * pending timer and in-flight work; drags (a held button) and map motion are
 * never sampled.
 */
export class HoverReadoutScheduler<T> {
  private timer: ReturnType<typeof setTimeout> | undefined;

  constructor(
    private readonly delayMs: number,
    private readonly isMapMoving: () => boolean,
    private readonly run: (target: T) => void,
    private readonly cancelInFlight: () => void,
  ) {}

  move(target: T, buttons: number): void {
    this.stop();
    if (buttons !== 0) return;
    this.timer = setTimeout(() => {
      this.timer = undefined;
      if (!this.isMapMoving()) this.run(target);
    }, this.delayMs);
  }

  stop(): void {
    if (this.timer !== undefined) {
      clearTimeout(this.timer);
      this.timer = undefined;
    }
    this.cancelInFlight();
  }
}
