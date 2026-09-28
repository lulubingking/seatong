/** @type {import('tailwindcss').Config} */
// 【纪律】本文件不得出现十六进制字面量。
// 所有取值一律引用 tokens.css 的 CSS 变量，保证「令牌唯一来源」。
// 违反即产生令牌漂移（D9 §9.3 校验会失败）。
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        surface: {
          DEFAULT: 'var(--surface)',
          2: 'var(--surface-2)',
          3: 'var(--surface-3)',
        },
        line: {
          DEFAULT: 'var(--border)',
          strong: 'var(--border-strong)',
        },
        ink: {
          DEFAULT: 'var(--text)',
          2: 'var(--text-2)',
          3: 'var(--text-3)',
          deep: 'var(--ink)',
        },
        brand: {
          DEFAULT: 'var(--primary)',
          600: 'var(--primary-600)',
          50: 'var(--primary-50)',
          100: 'var(--primary-100)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          50: 'var(--accent-50)',
          border: 'var(--accent-border)',
        },
        warn: {
          DEFAULT: 'var(--warn)',
          50: 'var(--warn-50)',
          border: 'var(--warn-border)',
        },
        danger: {
          DEFAULT: 'var(--danger)',
          50: 'var(--danger-50)',
          border: 'var(--danger-border)',
        },
        ok: {
          DEFAULT: 'var(--success)',
          50: 'var(--success-50)',
          border: 'var(--success-border)',
        },
        metric: {
          DEFAULT: 'var(--metric)',
          deep: 'var(--metric-deep)',
        },
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        DEFAULT: 'var(--radius)',
        lg: 'var(--radius-lg)',
      },
      boxShadow: {
        ring: 'var(--ring)',
      },
      fontFamily: {
        sans: 'var(--font)',
        mono: 'var(--mono)',
      },
      zIndex: {
        base: '2',
        topbar: '60',
        mask: '200',
        toast: '300',
      },
    },
  },
  plugins: [],
}
