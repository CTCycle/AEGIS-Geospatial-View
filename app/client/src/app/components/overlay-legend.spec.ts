import {
  HoverReadoutScheduler,
  formatHoverReadout,
  legendGradient,
  legendTicks,
  sampleCacheKey,
} from './overlay-legend';

describe('overlay legend scale', () => {
  const ramp = Array.from({ length: 250 }, (_, index) => ({
    color: `#${index.toString(16).padStart(2, '0')}0000`,
    value: 250 + (index * 80) / 249,
    label: '',
  }));

  it('downsamples long ramps to at most 32 value-positioned stops', () => {
    const stops = legendGradient([...ramp].reverse()).replace('linear-gradient(to right, ', '').slice(0, -1).split(', ');
    expect(stops.length).toBe(32);
    expect(stops[0]).toBe('#000000 0%');
    expect(stops[31]).toBe('#f90000 100%');
  });

  it('places stops of an unevenly spaced ramp by value', () => {
    expect(legendGradient([
      { color: '#000000', value: 0, label: '' },
      { color: '#888888', value: 1, label: '' },
      { color: '#ffffff', value: 4, label: '' },
    ])).toBe('linear-gradient(to right, #000000 0%, #888888 25%, #ffffff 100%)');
  });

  it('places round-valued ticks by value with units on the last one', () => {
    const ticks = legendTicks([
      { color: '#000000', value: 100, label: '' },
      { color: '#ffffff', value: 501, label: '' },
    ], 'K');
    expect(ticks.map((tick) => tick.label)).toEqual(['100', '200', '300', '400', '500 K']);
    expect(ticks[0].position).toBe(0);
    expect(ticks[2].position).toBeCloseTo(49.88, 2);
    expect(legendTicks([{ color: '#38bdf8', value: 0, label: '' }, { color: '#ef4444', value: 1, label: '' }], null)
      .map((tick) => tick.label)).toEqual(['0', '0.25', '0.5', '0.75', '1']);
  });

  it('collapses a single-value range to one tick', () => {
    expect(legendTicks([{ color: '#ef4444', value: 3, label: '' }, { color: '#38bdf8', value: 3, label: '' }], null))
      .toEqual([{ position: 0, label: '3' }]);
  });

  it('formats readouts for values, categories and nodata', () => {
    expect(formatHoverReadout({ kind: 'continuous', value: 301.54, label: '', units: 'K' }, 12.4912, 41.9028))
      .toBe('≈ 301.5 K · 41.90, 12.49');
    expect(formatHoverReadout({ kind: 'categorical', value: 10, label: 'Tree cover', units: null }, 0, 0))
      .toBe('Tree cover · 0.00, 0.00');
    expect(formatHoverReadout(null, 0, 0)).toBe('— · 0.00, 0.00');
  });

  it('shares a cache key within one tile pixel but not across pixels or times', () => {
    const base = sampleCacheKey('lst', 4, 12.49, 41.9, '2026-11-01');
    expect(sampleCacheKey('lst', 4, 12.5, 41.9, '2026-11-01')).toBe(base);
    expect(sampleCacheKey('lst', 4, 14, 41.9, '2026-11-01')).not.toBe(base);
    expect(sampleCacheKey('lst', 4, 12.49, 41.9, '2026-11-02')).not.toBe(base);
  });
});

describe('HoverReadoutScheduler', () => {
  let moving: boolean;
  let runs: string[];
  let cancels: number;
  let scheduler: HoverReadoutScheduler<string>;

  beforeEach(() => {
    jasmine.clock().install();
    moving = false;
    runs = [];
    cancels = 0;
    scheduler = new HoverReadoutScheduler<string>(150, () => moving, (target) => runs.push(target), () => { cancels += 1; });
  });

  afterEach(() => jasmine.clock().uninstall());

  it('runs once for the last position after the pointer rests', () => {
    scheduler.move('a', 0);
    jasmine.clock().tick(100);
    scheduler.move('b', 0);
    jasmine.clock().tick(149);
    expect(runs).toEqual([]);
    jasmine.clock().tick(1);
    expect(runs).toEqual(['b']);
    expect(cancels).toBe(2);
  });

  it('skips drags and map motion', () => {
    scheduler.move('drag', 1);
    jasmine.clock().tick(200);
    moving = true;
    scheduler.move('animating', 0);
    jasmine.clock().tick(200);
    expect(runs).toEqual([]);
  });

  it('stop cancels a pending run', () => {
    scheduler.move('a', 0);
    scheduler.stop();
    jasmine.clock().tick(200);
    expect(runs).toEqual([]);
  });
});
