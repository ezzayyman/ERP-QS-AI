/** @type {import('tailwindcss').Config} */
import colors from 'tailwindcss/colors';

// Semantic colour tokens are CSS variables (see src/index.css), so the whole app can be
// re-themed in one place.
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

// The app uses a dark theme. Older screens still use Tailwind's light utility classes
// (bg-white, bg-slate-50, text-slate-800, bg-emerald-50 …); flipping each palette's shade
// scale (50 <-> 950, 100 <-> 900, …) turns them into their dark-theme equivalents without
// touching every component. "white" follows the surface token for the same reason.
const SHADES = ['50', '100', '200', '300', '400', '500', '600', '700', '800', '900', '950'];
const invert = (palette) =>
  Object.fromEntries(SHADES.map((s, i) => [s, palette[SHADES[SHADES.length - 1 - i]]]));
const FAMILIES = ['slate', 'gray', 'zinc', 'neutral', 'stone', 'red', 'orange', 'amber', 'yellow', 'lime', 'green',
  'emerald', 'teal', 'cyan', 'sky', 'blue', 'indigo', 'violet', 'purple', 'fuchsia', 'pink', 'rose'];
const inverted = Object.fromEntries(FAMILIES.map((f) => [f, invert(colors[f])]));

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ...inverted,
        white: token('surface'),
        app: token('app'),
        surface: token('surface'),
        raised: token('raised'),
        sunken: token('sunken'),
        line: token('line'),
        'line-strong': token('line-strong'),
        ink: {
          DEFAULT: token('ink'),
          2: token('ink-2'),
          3: token('ink-3'),
        },
        accent: {
          DEFAULT: token('accent'),
          strong: token('accent-strong'),
          soft: token('accent-soft'),
          ink: token('accent-ink'),
        },
        ok: { DEFAULT: token('ok'), soft: token('ok-soft') },
        warn: { DEFAULT: token('warn'), soft: token('warn-soft') },
        danger: { DEFAULT: token('danger'), soft: token('danger-soft') },
        canvas: token('canvas'),
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['"Cormorant Garamond"', 'Georgia', 'serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        float: '0 1px 2px rgb(0 0 0 / 0.4), 0 8px 24px -6px rgb(0 0 0 / 0.6)',
        panel: '0 1px 2px rgb(0 0 0 / 0.3)',
      },
      borderRadius: {
        xl: '0.75rem',
      },
    },
  },
  plugins: [],
}
