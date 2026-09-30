import { router } from 'expo-router';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader, EmptyState } from '@/components/ui';
import { formatWon, monthlyAmount, nextBillingDate, totalMonthly, usageCount } from '@/domain/engine';
import { CATEGORY_LABEL } from '@/domain/types';
import { useAppStore } from '@/store/AppStore';
import { colors, font, radius, space } from '@/theme/tokens';

export default function Home() {
  const { subscriptions, usageLogs, checkIn } = useAppStore();
  const goAdd = () => router.push('/subscription/new');

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <AppHeader />
      {subscriptions.length === 0 ? (
        <EmptyState
          icon="credit-card"
          title="아직 등록된 구독이 없어요"
          description={'첫 구독을 추가하면 결제일과 월 지출을 한눈에\n관리할 수 있어요.'}
          actionLabel="첫 구독 추가하기"
          onAction={goAdd}
        />
      ) : (
        <FlatList
          data={subscriptions}
          keyExtractor={(s) => s.id}
          contentContainerStyle={{ padding: space.xl, gap: space.md }}
          ListHeaderComponent={
            <View style={styles.summary}>
              <Text style={font.caption}>이번 달 구독료</Text>
              <Text style={styles.total}>{formatWon(totalMonthly(subscriptions))}</Text>
              <Pressable onPress={goAdd}>
                <Text style={styles.addLink}>+ 구독 추가</Text>
              </Pressable>
            </View>
          }
          renderItem={({ item }) => {
            const next = nextBillingDate(item);
            return (
              <View style={styles.row}>
                <View style={{ flex: 1 }}>
                  <Text style={font.label}>{item.name}</Text>
                  <Text style={font.caption}>
                    {CATEGORY_LABEL[item.category]} · 다음 결제 {next.getMonth() + 1}/{next.getDate()}
                    {item.trackUsage ? ` · 30일 ${usageCount(usageLogs, item.id, 30)}회` : ''}
                  </Text>
                </View>
                <Text style={[font.label, { marginRight: space.md }]}>{formatWon(monthlyAmount(item))}</Text>
                {item.trackUsage && (
                  // PRD F2 원탭 체크인 — 시안에 없어 임시 배치
                  <Pressable style={styles.checkIn} onPress={() => checkIn(item.id)}>
                    <Text style={styles.checkInText}>썼어요</Text>
                  </Pressable>
                )}
              </View>
            );
          }}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  summary: { backgroundColor: colors.primarySoft, borderRadius: radius.lg, padding: space.xl, marginBottom: space.sm },
  total: { fontSize: 28, fontWeight: '800', color: colors.text, marginVertical: space.sm },
  addLink: { color: colors.primary, fontWeight: '700' },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: space.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  checkIn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 6 },
  checkInText: { color: '#fff', fontSize: 12, fontWeight: '700' },
});
