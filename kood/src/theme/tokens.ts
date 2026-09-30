// 디자인 시안(Figma) 기준 토큰. 색/간격은 여기서만 바꾼다.
export const colors = {
  primary: '#FF6B2C',
  primarySoft: '#FFF1E8',
  primarySofter: '#FFF7F2',
  text: '#111111',
  textSub: '#555555',
  textMuted: '#8B8B8B',
  surface: '#F5F5F7',
  border: '#ECECEC',
  bg: '#FFFFFF',
  success: '#16A34A',
  successSoft: '#E8F7EE',
  danger: '#E5484D',
} as const;

export const radius = { sm: 8, md: 12, lg: 16, xl: 24, pill: 999 } as const;

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 32 } as const;

export const font = {
  logo: { fontSize: 22, fontWeight: '800' as const, color: colors.text },
  title: { fontSize: 20, fontWeight: '700' as const, color: colors.text },
  heading: { fontSize: 18, fontWeight: '700' as const, color: colors.text },
  body: { fontSize: 14, color: colors.textSub },
  label: { fontSize: 13, fontWeight: '600' as const, color: colors.text },
  caption: { fontSize: 12, color: colors.textMuted },
};
