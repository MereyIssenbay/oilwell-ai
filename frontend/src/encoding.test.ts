import { expect, it } from 'vitest';
const source = import.meta.glob('./**/*.{tsx,ts,css}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
it('keeps source text UTF-8 without common CP1251/UTF-8 mojibake', () => {
  // Unicode escapes avoid putting the prohibited sequences in this test source.
  const broken = /\u0412\u00b7|\u0413\u2014|\u0432\u2020|\u0432\u0402|\ufffd/;
  for (const [path, text] of Object.entries(source)) expect(text, path).not.toMatch(broken);
});
