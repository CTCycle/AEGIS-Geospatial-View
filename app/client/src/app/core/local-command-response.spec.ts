import { buildDirectAnswerFromResult, formatCapabilitySummary, formatKnownLocations } from './local-command-response';

describe('core/local-command-response', () => {
  it('formats known locations', () => {
    expect(formatKnownLocations([' Rome ', 'Milan'])).toBe('Known locations: Rome, Milan.');
  });

  it('formats capability summary', () => {
    const text = formatCapabilitySummary({ capabilities: [], basemaps: [{ id: 'a' } as never], overlays: [{ id: 'b' } as never], tools: [{ id: 'c' } as never] });
    expect(text).toBe('Current catalog: 1 map types, 1 layers, and 1 direct tools.');
  });

  it('formats direct answer from result', () => {
    expect(buildDirectAnswerFromResult(' hello ')).toBe('hello');
    expect(buildDirectAnswerFromResult('')).toBe('No result available.');
    expect(buildDirectAnswerFromResult({ ok: true })).toBe('{"ok":true}');
  });
});