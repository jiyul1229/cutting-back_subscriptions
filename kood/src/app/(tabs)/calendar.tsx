// PRD F4: 해지 캘린더 — 시안 나오기 전까지 다가오는 결제/해지 권장 기간 리스트로 대체
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from '@/components/ui';
import { cancelWindow, formatWon } from '@/domain/engine';
import { useAppStore } from '@/store/AppStore';
import { colors, font, radius, space } from '@/theme/tokens';

const md = (d: Date) => `${d.getMonth() + 1}/${d.getDate()}`;

export default function CalendarScreen() {
  const { subscriptions } = useAppStore();
  const items = subscriptions
    .map((s) => ({ s, w: cancelWindow(s) }))
    .sort((a, b) => a.w.due.getTime() - b.w.due.getTime());

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <AppHeader />
      <Text style={[font.title, { paddingHorizontal: space.xl, paddingVertical: space.lg }]}>캘린더</Text>
      <ScrollView contentContainerStyle={{ paddingHorizontal: space.xl, gap: space.md }}>
        {items.length === 0 && <Text style={font.caption}>등록된 구독이 없어요.</Text>}
        {items.map(({ s, w }) => (
          <View key={s.id} style={styles.row}>
            <Text style={styles.date}>{md(w.due)}</Text>
            <View style={{ flex: 1 }}>
              <Text style={font.label}>{s.name} · {formatWon(s.amount)}</Text>
              <Text style={font.caption}>해지 권장 {md(w.start)} ~ {md(w.end)}</Text>
            </View>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.lg,
    padding: space.lg,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
  },
  date: { fontSize: 16, fontWeight: '800', color: colors.primary, width: 48 },
});
