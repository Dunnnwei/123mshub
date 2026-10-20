/** Export the actual local HAUI resolver, never a hand-recreated palette.
 * Usage: node scripts/native/sync-haui.mjs [path-to-HAUI]
 * Run `npm run build:lib` in HAUI first. Generated runtime files are committed.
 */
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from 'node:fs';
import { dirname, resolve, join } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const source = resolve(process.argv[2] || join(root, '../HAUI'));
const requireSource = createRequire(join(source, 'package.json'));
const { createElement } = requireSource('react');
const { renderToStaticMarkup } = requireSource('react-dom/server');
const h = await import(pathToFileURL(join(source, 'packages/haui/dist/index.js')));
const out = join(root, 'src/mshub/native/haui');
mkdirSync(out, { recursive: true });
const manifest = { system: 'HAUI', version: '0.1.0', adapterVersion: 1, sources: {}, outputs: {} };
const hash = data => createHash('sha256').update(data).digest('hex');
function record(file) { manifest.sources[file] = hash(readFileSync(join(source, file))); }
function write(file, data) {
  mkdirSync(dirname(join(out, file)), { recursive: true });
  writeFileSync(join(out, file), data);
  manifest.outputs[file] = hash(data);
}
function copy(file, dest) { record(file); write(dest, readFileSync(join(source, file))); }
for (const file of ['packages/haui/src/themes/palette-data.json', 'packages/haui/src/themes/presets.ts',
  'packages/haui/src/themes/color.ts', 'packages/haui/src/themes/resolve.ts', 'packages/haui/src/themes/provider.tsx',
  'packages/haui/src/tokens.css', 'packages/haui/src/icons.ts']) record(file);
const accents = [
  ['default', '调色板默认', null], ['blue', '蓝色', '#0053fd'], ['green', '绿色', '#19845b'],
  ['amber', '琥珀', '#ad7500'], ['rose', '玫瑰', '#b14470'], ['violet', '紫色', '#7955cf'],
  ['teal', '青色', '#008580'], ['orange', '橙色', '#bc591d'], ['slate', '石板', '#64748b'],
];
function projected(c, mode) {
  const blend = (color, ratio) => h.mix(c.background, color, ratio);
  const text = ratio => h.ensureContrast(blend(c.foreground, ratio), c.background);
  const ink = text(.94), muted = text(.80), faint = text(.65);
  // HAUI's off-black/white ink choice can narrowly miss AA near mid luminance.
  // Preserve the raw seed; adjust only the native filled control projection.
  const action = h.ensureContrast(c.primary, h.readableInk(c.primary));
  const accent = h.ensureContrast(c.midground, c.background);
  const typeSeed = ['github', 'everforest', 'catppuccin', 'classic'];
  const types = Object.fromEntries(['user', 'project', 'reference', 'feedback'].map((key, i) =>
    [key, h.ensureContrast(h.paletteFor(h.themeRegistry[typeSeed[i]], mode).primary, c.background)]));
  return {
    bg: c.background, sidebar: c.sidebarBackground, surface: c.background, raised: c.popover,
    inset: blend(c.midground, .03), ink, muted, faint, disabled: blend(c.foreground, .45),
    line: blend(c.midground, .10), strong: blend(c.midground, .24), action, on_action: h.readableInk(action),
    accent, selection: blend(c.midground, .08), hover: blend(c.midground, .04),
    control: blend(c.midground, .05), control_hover: blend(c.midground, .06),
    action_hover: h.mix(action, c.foreground, .12), action_pressed: h.mix(action, c.foreground, .20),
    accent_hover: accent, error: h.ensureContrast(c.destructive, c.background), error_soft: blend(c.destructive, .08),
    ok: h.ensureContrast('#19845b', c.background), ok_soft: blend('#19845b', .08),
    warning: h.ensureContrast('#ad7500', c.background), warning_soft: blend('#ad7500', .08),
    glass: c.popover, star_dot: c.midground, star_bright: c.midground, graph_line: blend(c.foreground, .18),
    action_gradient_start: action, action_gradient_end: action, sheet_alpha: 255,
    sidebar_ink: h.ensureContrast(c.foreground, c.sidebarBackground), sidebar_line: c.sidebarBorder,
    ...types,
  };
}
const themes = {};
for (const theme of h.getThemes()) {
  const variants = {};
  for (const [id, , seed] of accents) {
    variants[id] = {};
    for (const mode of ['light', 'dark']) {
      const colors = h.accentedPalette(theme, mode, seed);
      variants[id][mode] = { seeds: colors, renderedMode: h.renderedModeFor(colors), qt: projected(colors, mode) };
    }
  }
  themes[theme.id] = { label: theme.label, variants };
}
write('themes.json', JSON.stringify({ system: 'HAUI', version: '0.1.0', defaultPalette: 'nous',
  accents: accents.map(([id, label, color]) => ({ id, label, color })), themes }, null, 2) + '\n');
const names = {
  memory: 'BookIcon', graph: 'LayersIcon', skills: 'ComponentsIcon', security: 'SuccessIcon', settings: 'SettingsIcon',
  note_new: 'FileIcon', edit: 'SlidersIcon', delete: 'TrashIcon', refresh: 'UndoIcon', trust: 'SuccessIcon',
  agent: 'CommandIcon', ai: 'BoltIcon', auto: 'BoltIcon', copy: 'CopyIcon', inbox: 'InboxIcon', list: 'MenuIcon',
  add: 'PlusIcon', scan: 'SearchIcon', translate: 'MessageIcon', update: 'DownloadIcon', save: 'CheckIcon',
  folder: 'FolderIcon', import: 'DownloadIcon', clear: 'CloseIcon', download: 'DownloadIcon', network: 'ActivityIcon',
  info: 'ErrorIcon', close: 'CloseIcon', eye: 'FileIcon', open: 'ExternalLinkIcon', chevron_up: 'ArrowUpIcon',
  chevron_down: 'ChevronDownIcon', tag: 'LayersIcon', search: 'SearchIcon', shield: 'SuccessIcon',
};
const icons = Object.fromEntries(Object.entries(names).map(([name, exp]) => [name,
  renderToStaticMarkup(createElement(h[exp], { size: 24, stroke: 1.7, color: 'COLOR' })).replaceAll('currentColor', 'COLOR'),
]));
write('icons.json', JSON.stringify(icons, null, 2) + '\n');
for (const [name, color] of [['light', '#ffffff'], ['dark', '#161616']]) {
  write(`check-${name}.svg`, renderToStaticMarkup(createElement(h.CheckIcon, { size: 16, stroke: 2.2, color })).replaceAll('currentColor', color));
  write(`chevron-${name}.svg`, renderToStaticMarkup(createElement(h.ChevronDownIcon, { size: 16, stroke: 1.7, color })).replaceAll('currentColor', color));
}
for (const font of ['JetBrainsMono', 'SpaceGrotesk']) {
  copy(`packages/haui/src/fonts/${font}-Latin.woff2`, `fonts/${font}-Latin.woff2`);
  copy(`packages/haui/src/fonts/${font}-OFL.txt`, `fonts/${font}-OFL.txt`);
}
copy('LICENSE', 'licenses/HAUI-MIT.txt');
copy('THIRD_PARTY_NOTICES.md', 'licenses/HAUI-NOTICES.md');
copy('node_modules/@tabler/icons/LICENSE', 'licenses/Tabler-MIT.txt');
for (const name of ['NousResearch', 'GitHub', 'Everforest', 'Catppuccin', 'Solarized'])
  copy(`licenses/palettes/${name}-MIT.txt`, `licenses/${name}-MIT.txt`);
writeFileSync(join(out, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`Exported ${Object.keys(themes).length} palettes, ${accents.length} accent choices and ${Object.keys(icons).length} Tabler icons from HAUI ${manifest.version}.`);
