import { Feather } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader, EmptyState, SegmentedControl } from '@/components/ui';
import { detectLowUsage, formatWon, monthlyAmount, totalMonthly, totalYearly } from '@/domain/engine';
import { CATEGORY_LABEL, type Category } from '@/domain/types';
import { useAppStore } from '@/store/AppStore';
import { colors, font, radius, space } from '@/theme/tokens';

type Mode = 'monthly' | 'category';

export default function Analysis() {
  const { subscriptions, usageLogs } = useAppStore();
  const [mode, setMode] = useState<Mode>('monthly');
  const empty = subscriptions.length === 0;

  const byCategory = Object.entries(
    subscriptions.reduce<Partial<Record<Category, number>>>((acc, s) => {
      acc[s.category] = (acc[s.category] ?? 0) + monthlyAmount(s);
      return acc;
    }, {}),
  ).sort((a, b) => b[1]! - a[1]!);
  const total = totalMonthly(subscriptions);
  const warnings = detectLowUsage(subscriptions, usageLogs);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <AppHeader />
      <View style={styles.titleRow}>
        <Text style={font.title}>지출 분석</Text>
        <Feather name="trending-up" size={18} color={colors.textSub} />
      </View>
      <View style={{ paddingHorizontal: space.xl }}>
        <SegmentedControl
          value={mode}
          onChange={setMode}
          options={[
            { value: 'monthly', label: '월별' },
            { value: 'category', label: '카테고리별' },
          ]}
        />
      </View>

      {empty ? (
        <EmptyState
          icon="bar-chart-2"
          title="분석할 데이터가 없어요"
          description={'구독을 추가하고 결제 기록이 쌓이면 지출 패턴\n과 절약 기회를 알려드려요.'}
          actionLabel="구독 추가하기"
          onAction={() => router.push('/subscription/new')}
        />
      ) : (
        <ScrollView contentContainerStyle={{ padding: space.xl, gap: space.md }}>
          {mode === 'monthly' ? (
            // TODO(프론트): 월별 추이 차트 (결제 이력 모델이 정해지면)
            <View style={styles.card}>
              <Text style={font.caption}>월 환산 / 연 환산</Text>
              <Text style={styles.big}>{formatWon(total)}</Text>
              <Text style={font.body}>연 {formatWon(totalYearly(subscriptions))}</Text>
            </View>
          ) : (
            byCategory.map(([cat, amt]) => (
              <View key={cat} style={styles.card}>
                <View style={styles.barLabel}>
                  <Text style={font.label}>{CATEGORY_LABEL[cat as Category]}</Text>
                  <Text style={font.label}>{formatWon(amt!)}</Text>
                </View>
                <View style={styles.barTrack}>
                  <View style={[styles.barFill, { width: `${(amt! / total) * 100}%` }]} />
                </View>
              </View>
            ))
          )}

          {warnings.length > 0 && (
            <View style={[styles.card, { backgroundColor: colors.primarySofter }]}>
              <Text style={[font.label, { marginBottom: space.sm }]}>잘 안 쓰는 구독</Text>
              {warnings.map((w) => {
                const s = subscriptions.find((x) => x.id === w.subscriptionId)!;
                return (
                  <Text key={w.subscriptionId} style={font.body}>
                    {s.name}: {w.reasons.join(', ')}
                    {w.costPerUse !== null ? ` · 이용 단가 ${formatWon(w.costPerUse)}/회` : ''}
                  </Text>
                );
              })}
            </View>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  titleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: space.xl,
    paddingTop: space.lg,
    paddingBottom: space.lg,
  },
  card: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: space.lg },
  big: { fontSize: 26, fontWeight: '800', color: colors.text, marginVertical: space.sm },
  barLabel: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: space.sm },
  barTrack: { height: 8, backgroundColor: colors.surface, borderRadius: radius.pill, overflow: 'hidden' },
  barFill: { height: 8, backgroundColor: colors.primary, borderRadius: radius.pill },
});
