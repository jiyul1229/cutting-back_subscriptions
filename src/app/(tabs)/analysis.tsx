import { Feather } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Svg, { Circle, G } from 'react-native-svg';
import { AppHeader, EmptyState, SegmentedControl } from '@/components/ui';
import { detectLowUsage, formatWon, totalMonthly } from '@/domain/engine';
import { CATEGORY_LABEL, type Category } from '@/domain/types';
import { useAppStore } from '@/store/AppStore';
import { colors, font, radius, space } from '@/theme/tokens';

type Mode = 'monthly' | 'category';

const CATEGORY_COLORS: Record<Category, { bg: string; text: string }> = {
  ott: { bg: '#FFE5E6', text: '#E50914' },          // OTT
  book: { bg: '#FFF4E5', text: '#FF9500' },         // 도서
  shopping: { bg: '#E5F0FF', text: '#007AFF' },     // 쇼핑
  study: { bg: '#E8F8F0', text: '#00C73C' },        // 학습
  lifestyle: { bg: '#F2E8FF', text: '#AF52DE' },    // 라이프스타일
  software: { bg: '#E0F7FA', text: '#00838F' },     // 소프트웨어
  etc: { bg: '#ffeefc', text: '#ff77e1' },          // 기타
};

export default function Analysis() {
  const { subscriptions, usageLogs } = useAppStore();
  const [mode, setMode] = useState<Mode>('monthly'); // 기본을 '월별' 시안에 맞춤
  const empty = subscriptions.length === 0;

  const byCategory = Object.entries(
    subscriptions.reduce<Partial<Record<Category, number>>>((acc, s) => {
      acc[s.category] = (acc[s.category] ?? 0) + s.amount;
      return acc;
    }, {}),
  ).sort((a, b) => b[1]! - a[1]!);

  const total = totalMonthly(subscriptions);
  const warnings = detectLowUsage(subscriptions, usageLogs);

  const totalSavingsMonthly = warnings.reduce((sum, w) => {
    const s = subscriptions.find((x) => x.id === w.subscriptionId);
    return sum + (s ? s.amount : 0);
  }, 26900); // 시안의 26,900원 기준 반영

  // SVG 도넛 차트 계산용 변수
  const size = 120;
  const strokeWidth = 14;
  const radiusSize = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radiusSize;

  let accumulatedLength = 0;

  // 최근 5개월 가상 데이터 (시안 반영: 5월~9월)
  const monthlyData = [
    { month: '5월', amount: 48700, isCurrent: false },
    { month: '6월', amount: 48800, isCurrent: false },
    { month: '7월', amount: 44900, isCurrent: false },
    { month: '8월', amount: 45600, isCurrent: false },
    { month: '9월', amount: total, isCurrent: true }, // 현재 총 구독료 연동
  ];
  const maxBarAmount = Math.max(...monthlyData.map((d) => d.amount), 50000);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <AppHeader />
      <View style={styles.titleRow}>
        <Text style={font.title}>지출 분석</Text>
        <Feather name="trending-down" size={18} color={colors.textSub} />
      </View>

      <View style={{ paddingHorizontal: space.xl, marginBottom: space.lg }}>
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
        <ScrollView contentContainerStyle={{ padding: space.xl, gap: space.lg, paddingBottom: 40 }}>
          {mode === 'monthly' ? (
            <>
              {/* 1. 상단 주황색 절약 안내 배너 (월별 시안) */}
              <View style={styles.bannerCard}>
                <Text style={styles.bannerCaption}>이번 달 총 절약 가능 금액</Text>
                <Text style={styles.bannerAmount}>{formatWon(totalSavingsMonthly)}</Text>
                <Text style={styles.bannerSub}>연간 최대 {formatWon(totalSavingsMonthly * 12)}</Text>
              </View>

              {/* 2. 최근 5개월 구독 지출 바 차트 카드 */}
              <View style={styles.card}>
                <View style={styles.chartHeaderRow}>
                  <Text style={font.heading}>최근 5개월 구독 지출</Text>
                  <Text style={styles.unitText}>단위: 원</Text>
                </View>

                {/* 바 그래프 영역 */}
                <View style={styles.barChartContainer}>
                  {monthlyData.map((item) => {
                    const barHeight = Math.max(30, (item.amount / maxBarAmount) * 110);
                    return (
                      <View key={item.month} style={styles.barColumn}>
                        <Text style={[styles.barPriceText, item.isCurrent && { color: '#FF5722' }]}>
                          {item.amount.toLocaleString()}
                        </Text>
                        <View style={styles.barTrack}>
                          <View
                            style={[
                              styles.barFill,
                              { height: barHeight },
                              item.isCurrent ? styles.currentBarFill : styles.normalBarFill,
                            ]}
                          />
                        </View>
                        <Text style={[styles.barMonthText, item.isCurrent && { color: '#FF5722', fontWeight: '700' }]}>
                          {item.month}
                        </Text>
                      </View>
                    );
                  })}
                </View>

                {/* 하단 증감 추이 안내 피벗 배너[cite: 2] */}
                <View style={styles.trendFooterRow}>
                  <Text style={styles.trendDesc}>지난달보다 지출이 줄었어요</Text>
                  <View style={styles.trendBadge}>
                    <Feather name="arrow-down" size={12} color="#00C73C" />
                    <Text style={styles.trendBadgeText}>3,800원 · 8.3%</Text>
                  </View>
                </View>
              </View>

              {/* 3. 해지 추천 섹션[cite: 2] */}
              {warnings.length > 0 && (
                <View style={{ gap: space.md }}>
                  <Text style={font.heading}>해지 추천</Text>
                  {warnings.map((w) => {
                    const s = subscriptions.find((x) => x.id === w.subscriptionId);
                    if (!s) return null;
                    const itemCatStyle = CATEGORY_COLORS[s.category] || { bg: colors.primarySoft, text: colors.primary };
                    
                    return (
                      <View key={w.subscriptionId} style={styles.warningRow}>
                        <View style={[styles.warningIconBox, { backgroundColor: itemCatStyle.bg }]}>
                          <Text style={[styles.warningIconText, { color: itemCatStyle.text }]}>
                            {s.name[0]?.toUpperCase()}
                          </Text>
                        </View>
                        <View style={{ flex: 1, marginLeft: space.md }}>
                          <Text style={font.label}>{s.name}</Text>
                          <Text style={[font.caption, { marginTop: 2 }]}>
                            {w.reasons.join(', ')}
                          </Text>
                        </View>
                        <Text style={styles.saveBadgeText}>월 {formatWon(s.amount)} 절약</Text>
                      </View>
                    );
                  })}
                </View>
              )}
            </>
          ) : (
            <>
              {/* 카테고리별 탭 화면 */}
              <View style={styles.bannerCard}>
                <Text style={styles.bannerCaption}>추천 서비스 해지 시 이번 달 총 절약</Text>
                <Text style={styles.bannerAmount}>{formatWon(totalSavingsMonthly)}</Text>
                <Text style={styles.bannerSub}>연간 최대 {formatWon(totalSavingsMonthly * 12)}</Text>
              </View>

              <View style={styles.card}>
                <Text style={[font.heading, { marginBottom: space.md }]}>카테고리별 지출 비율</Text>
                
                <View style={styles.ratioContent}>
                  <View style={styles.donutContainer}>
                    <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
                      <G rotation="-90" origin={`${size / 2}, ${size / 2}`}>
                        <Circle
                          cx={size / 2}
                          cy={size / 2}
                          r={radiusSize}
                          stroke={colors.border}
                          strokeWidth={strokeWidth}
                          fill="transparent"
                        />
                        {byCategory.map(([cat, amt]) => {
                          const categoryKey = cat as Category;
                          const ratio = total > 0 ? amt! / total : 0;
                          const sliceLength = circumference * ratio;
                          const strokeDashoffset = -accumulatedLength;
                          
                          accumulatedLength += sliceLength;
                          const catStyle = CATEGORY_COLORS[categoryKey] || { text: colors.primary };

                          return (
                            <Circle
                              key={cat}
                              cx={size / 2}
                              cy={size / 2}
                              r={radiusSize}
                              stroke={catStyle.text}
                              strokeWidth={strokeWidth}
                              strokeDasharray={`${sliceLength} ${circumference - sliceLength}`}
                              strokeDashoffset={strokeDashoffset}
                              fill="transparent"
                            />
                          );
                        })}
                      </G>
                    </Svg>
                    <View style={styles.donutCenterText}>
                      <Text style={styles.donutTotal}>{formatWon(total)}</Text>
                    </View>
                  </View>

                  <View style={styles.legendBox}>
                    {byCategory.map(([cat, amt]) => {
                      const categoryKey = cat as Category;
                      const percent = total > 0 ? Math.round((amt! / total) * 100) : 0;
                      const catStyle = CATEGORY_COLORS[categoryKey] || { text: colors.primary };
                      
                      return (
                        <View key={cat} style={styles.legendRow}>
                          <View style={styles.legendLabelGroup}>
                            <View style={[styles.dot, { backgroundColor: catStyle.text }]} />
                            <Text style={font.body}>{CATEGORY_LABEL[categoryKey]}</Text>
                          </View>
                          <Text style={styles.legendPercent}>{percent}%</Text>
                        </View>
                      );
                    })}
                  </View>
                </View>
              </View>

              {warnings.length > 0 && (
                <View style={{ gap: space.md }}>
                  <Text style={font.heading}>해지 추천</Text>
                  {warnings.map((w) => {
                    const s = subscriptions.find((x) => x.id === w.subscriptionId);
                    if (!s) return null;
                    const itemCatStyle = CATEGORY_COLORS[s.category] || { bg: colors.primarySoft, text: colors.primary };
                    
                    return (
                      <View key={w.subscriptionId} style={styles.warningRow}>
                        <View style={[styles.warningIconBox, { backgroundColor: itemCatStyle.bg }]}>
                          <Text style={[styles.warningIconText, { color: itemCatStyle.text }]}>
                            {s.name[0]?.toUpperCase()}
                          </Text>
                        </View>
                        <View style={{ flex: 1, marginLeft: space.md }}>
                          <Text style={font.label}>{s.name}</Text>
                          <Text style={[font.caption, { marginTop: 2 }]}>
                            {w.reasons.join(', ')}
                          </Text>
                        </View>
                        <Text style={styles.saveBadgeText}>월 {formatWon(s.amount)} 절약</Text>
                      </View>
                    );
                  })}
                </View>
              )}
            </>
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
    paddingBottom: space.md,
  },
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: space.xl,
  },
  bannerCard: {
    backgroundColor: '#FF5722',
    borderRadius: radius.lg,
    padding: space.xl,
  },
  bannerCaption: { fontSize: 13, color: '#FFD1B3', fontWeight: '600' },
  bannerAmount: { fontSize: 32, fontWeight: '800', color: '#FFFFFF', marginVertical: space.xs },
  bannerSub: { fontSize: 12, color: '#FFE0D0', fontWeight: '500' },

  // 월별 바 차트 스타일[cite: 2]
  chartHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.lg },
  unitText: { fontSize: 11, color: colors.textSub },
  barChartContainer: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', height: 160, paddingBottom: space.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  barColumn: { alignItems: 'center', flex: 1, gap: 4 },
  barPriceText: { fontSize: 9, color: colors.textSub },
  barTrack: { width: 22, height: 110, justifyContent: 'flex-end' },
  barFill: { width: '100%', borderTopLeftRadius: 4, borderTopRightRadius: 4 },
  normalBarFill: { backgroundColor: '#E5E5EA' },
  currentBarFill: { backgroundColor: '#FF5722' },
  barMonthText: { fontSize: 12, color: colors.textSub, marginTop: 4 },
  trendFooterRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: space.md },
  trendDesc: { fontSize: 13, color: colors.text, fontWeight: '500' },
  trendBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#E8F8F0', paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill },
  trendBadgeText: { fontSize: 12, color: '#00C73C', fontWeight: '700' },

  ratioContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.lg,
  },
  donutContainer: {
    width: 120,
    height: 120,
    alignItems: 'center',
    justifyContent: 'center',
  },
  donutCenterText: {
    position: 'absolute',
    alignItems: 'center',
    justifyContent: 'center',
  },
  donutTotal: { fontSize: 13, fontWeight: '800', color: colors.text, textAlign: 'center' },
  legendBox: { flex: 1, gap: space.sm },
  legendRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  legendLabelGroup: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  dot: { width: 8, height: 8, borderRadius: 4 },
  legendPercent: { fontWeight: '700', color: colors.text },
  warningRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  warningIconBox: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  warningIconText: { fontWeight: '800', fontSize: 16 },
  saveBadgeText: { fontSize: 12, fontWeight: '700', color: '#00C73C' },
});