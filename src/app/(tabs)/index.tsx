import { Feather } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { SubscriptionDetailModal } from '@/components/SubscriptionDetailModal';
import { AppHeader, EmptyState } from '@/components/ui';
import { formatWon, nextBillingDate, totalMonthly } from '@/domain/engine';
import { type Category, type Subscription } from '@/domain/types';
import { useAppStore } from '@/store/AppStore';
import { colors, font, radius, space } from '@/theme/tokens';

const CATEGORY_COLORS: Record<Category, { bg: string; text: string }> = {
  ott: { bg: '#FFE5E6', text: '#E50914' },
  book: { bg: '#FFF4E5', text: '#FF9500' },
  shopping: { bg: '#E5F0FF', text: '#007AFF' },
  lifestyle: { bg: '#F2E8FF', text: '#AF52DE' },
  software: { bg: '#E0F7FA', text: '#00838F' },
  study: { bg: '#E8F5E9', text: '#2E7D32' },
  etc: { bg: '#ffeefc', text: '#ff77e1' },
};

export default function Home() {
  const { subscriptions, removeSubscription } = useAppStore();
  const [selectedSub, setSelectedSub] = useState<Subscription | null>(null);
  
  const goAdd = () => router.push('/subscription/new');

  const nearestSub = subscriptions.length > 0 ? subscriptions[0] : null;
  const nearestDate = nearestSub ? nextBillingDate(nearestSub) : null;

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
            <View style={{ gap: space.md, marginBottom: space.md }}>
              <View style={styles.summaryCard}>
                <Text style={styles.summaryCaption}>이번 달 총 구독료</Text>
                <Text style={styles.totalAmount}>{formatWon(totalMonthly(subscriptions))}</Text>
                <View style={styles.summaryFooter}>
                  <View style={styles.badgeRow}>
                    <Feather name="arrow-down" size={12} color="#4CD964" />
                    <Text style={styles.badgeText}>전월 대비 8.4%</Text>
                  </View>
                  <Text style={styles.activeCount}>활성 구독 {subscriptions.length}개</Text>
                </View>
              </View>

              {nearestSub && nearestDate && (
                <Pressable style={styles.alertCard} onPress={() => router.push('/(tabs)/calendar')}>
                  <View style={styles.alertLeft}>
                    <View style={styles.brandIconBox}>
                      <Text style={styles.brandIconText}>{nearestSub.name[0]?.toUpperCase()}</Text>
                    </View>
                    <View>
                      <Text style={styles.alertLabel}>가장 빠른 결제 예정</Text>
                      <Text style={styles.alertTitle}>
                        {nearestSub.name} · {nearestDate.getMonth() + 1}월 {nearestDate.getDate()}일
                      </Text>
                    </View>
                  </View>
                  <Text style={styles.alertPrice}>{formatWon(nearestSub.amount)}</Text>
                </Pressable>
              )}

              <View style={styles.sectionHeader}>
                <Text style={font.heading}>활성 구독 ({subscriptions.length}개)</Text>
                <Pressable onPress={goAdd}>
                  <Text style={styles.addLink}>+ 구독 추가</Text>
                </Pressable>
              </View>
            </View>
          }
          renderItem={({ item }) => {
            const catStyle = CATEGORY_COLORS[item.category] || { bg: colors.primarySoft, text: colors.primary };
            const firstLetter = item.name[0] ? item.name[0].toUpperCase() : 'S';

            return (
              /* 화살표나 행을 누르면 상세 보기 모달 오픈 */
              <Pressable style={styles.row} onPress={() => setSelectedSub(item)}>
                <View style={[styles.itemIconBox, { backgroundColor: catStyle.bg }]}>
                  <Text style={[styles.itemIconText, { color: catStyle.text }]}>{firstLetter}</Text>
                </View>

                <View style={{ flex: 1, marginLeft: space.md }}>
                  <Text style={font.label}>{item.name}</Text>
                  <Text style={[font.caption, { marginTop: 2 }]}>
                    {item.cycle === 'monthly' 
                      ? `결제일: 매월 ${item.billingDay}일` 
                      : `결제일: 매년 ${item.billingMonth}월 ${item.billingDay}일`}
                  </Text>
                </View>

                <View style={{ alignItems: 'flex-end', marginRight: space.sm }}>
                  <Text style={font.label}>{formatWon(item.amount)}</Text>
                </View>
                <Feather name="chevron-right" size={16} color={colors.textSub} />
              </Pressable>
            );
          }}
        />
      )}

      {/* 상세 보기 및 삭제 확인 모달 컴포넌트 */}
      <SubscriptionDetailModal
        visible={selectedSub !== null}
        subscription={selectedSub}
        onClose={() => setSelectedSub(null)}
        onDelete={(id) => removeSubscription(id)}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  summaryCard: { backgroundColor: '#1C1C1E', borderRadius: radius.xl, padding: space.xl },
  summaryCaption: { fontSize: 13, color: '#8E8E93', fontWeight: '600' },
  totalAmount: { fontSize: 32, fontWeight: '800', color: '#FFFFFF', marginVertical: space.sm },
  summaryFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: space.xs },
  badgeRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  badgeText: { fontSize: 12, color: '#4CD964', fontWeight: '700' },
  activeCount: { fontSize: 12, color: '#8E8E93' },
  alertCard: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#FFF5F2', borderWidth: 1, borderColor: '#FFEBE6', borderRadius: radius.lg, padding: space.lg },
  alertLeft: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  brandIconBox: { width: 36, height: 36, borderRadius: radius.sm, backgroundColor: '#E50914', alignItems: 'center', justifyContent: 'center' },
  brandIconText: { color: '#FFF', fontWeight: '800', fontSize: 16 },
  alertLabel: { fontSize: 11, color: '#FF3B30', fontWeight: '700', marginBottom: 2 },
  alertTitle: { fontSize: 13, fontWeight: '600', color: colors.text },
  alertPrice: { fontSize: 14, fontWeight: '800', color: colors.text },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: space.sm },
  addLink: { color: colors.primary, fontWeight: '700', fontSize: 13 },
  row: { flexDirection: 'row', alignItems: 'center', padding: space.lg, borderRadius: radius.lg, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  itemIconBox: { width: 40, height: 40, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
  itemIconText: { fontWeight: '800', fontSize: 16 },
});