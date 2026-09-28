import type { ThemeConfig } from 'antd'

/**
 * AntD5 主题对齐（D9 §10.2.3 / §3.11）
 *
 * 【要点】
 *  · 不写 !important 覆盖 AntD 样式，一律通过 theme.token / components.* 配置，
 *    以保持可升级性。
 *  · AntD 默认圆角 6px、默认主色（蓝）与本系统不符，必须显式覆盖。
 *  · 本期不实现暗色模式（D9 §0.5 范围声明），故不配置 algorithm。
 *
 * 【为什么可以用 var(--x)】ConfigProvider 的 token 接受字符串形式的任意 CSS 值，
 * 浏览器在计算时解析。这样令牌一改，AntD 与 Tailwind 同步生效，无需两处修改。
 */
export const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: 'var(--primary)',
    colorInfo: 'var(--accent)',
    colorWarning: 'var(--warn)',
    colorError: 'var(--danger)',
    colorSuccess: 'var(--success)',

    colorText: 'var(--text)',
    colorTextSecondary: 'var(--text-2)',
    colorTextTertiary: 'var(--text-3)',
    colorTextQuaternary: 'var(--text-3)',

    colorBgLayout: 'var(--bg)',
    colorBgContainer: 'var(--surface)',
    colorBgElevated: 'var(--surface)',

    colorBorder: 'var(--border-strong)',
    colorBorderSecondary: 'var(--border)',

    borderRadius: 10, // = --radius（AntD 默认 6px，必须显式覆盖）
    borderRadiusSM: 8, // = --radius-sm
    borderRadiusLG: 14, // = --radius-lg

    fontFamily: 'var(--font)',
    fontSize: 14,
    controlHeight: 36,
  },
  components: {
    Button: {
      controlHeight: 36,
      fontWeight: 600, // 按钮文字用强调字重（D9 §3.7）
      primaryShadow: 'none', // 禁止新增阴影
      defaultShadow: 'none',
      dangerShadow: 'none',
    },
    Table: {
      headerBg: 'var(--surface-3)',
      borderColor: 'var(--border)',
      rowHoverBg: 'var(--surface-2)',
      headerSplitColor: 'transparent',
    },
    Modal: { borderRadiusLG: 14 },
    Drawer: { paddingLG: 20 },
    Input: { activeShadow: 'var(--ring)' },
    Select: { optionSelectedBg: 'var(--primary-50)' },
    Tabs: { itemSelectedColor: 'var(--primary-600)', inkBarColor: 'var(--primary)' },
    Card: { borderRadiusLG: 14 },
    Menu: {
      itemSelectedBg: 'var(--primary-50)',
      itemSelectedColor: 'var(--primary-600)',
    },
  },
}
