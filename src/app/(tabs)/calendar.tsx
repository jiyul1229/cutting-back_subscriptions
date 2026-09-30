// PRD F4: 결제 캘린더 — 결제일 점 표시, 날짜 탭 → 해당일 결제 목록
import { Feather } from '@expo/vector-icons';
import { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from '@/components/ui';
import { billingsInMonth, cancelWindow, formatWon } from '@/domain/engine';
import { useAppStore } from '@/store/AppStore';
import { colors, font, radius, space } from '@/theme/tokens';

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

type Cell = { date: Date; inMonth: boolean };

/** 해당 월을 포함하는 주 단위 그리드 (앞뒤 달 날짜 포함) */
function buildGrid(year: number, month0: number): Cell[][] {
  const first = new Date(year, month0, 1);
  const start = new Date(year, month0, 1 - first.getDay());
  const lastDay = new Date(year, month0 + 1, 0).getDate();
  const weeks = Math.ceil((first.getDay() + lastDay) / 7);
  return Array.from({ length: weeks }, (_, w) =>
    Array.from({ length: 7 }, (_, d) => {
      const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + w * 7 + d);
      return { date, inMonth: date.getMonth() === month0 };
    }),
  );
}

const sameDay = (a: Date, b: Date) =>
  a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

export default function CalendarScreen() {
  const { subscriptions } = useAppStore();
  const today = new Date();
  const [cursor, setCursor] = useState({ y: today.getFullYear(), m: today.getMonth() });
  const [selected, setSelected] = useState<Date | null>(null);

  const grid = useMemo(() => buildGrid(cursor.y, cursor.m), [cursor]);
  const billings = useMemo(
    () => billingsInMonth(subscriptions, cursor.y, cursor.m),
    [subscriptions, cursor],
  );

  const move = (delta: number) => {
    const d = new Date(cursor.y, cursor.m + delta, 1);
    setCursor({ y: d.getFullYear(), m: d.getMonth() });
    setSelected(null);
  };

  // 선택한 날짜가 있으면 그날, 없으면 이번 달 전체 결제 목록
  const list = selected
    ? (billings.get(selected.getDate()) ?? []).map((s) => ({ s, day: selected.getDate() }))
    : [...billings.entries()]
        .sort((a, b) => a[0] - b[0])
        .flatMap(([day, subs]) => subs.map((s) => ({ s, day })));
  const monthTotal = [...billings.values()].flat().reduce((sum, s) => sum + s.amount, 0);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <AppHeader />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.titleRow}>
          <Text style={font.title}>결제 캘린더</Text>
          <Pressable
            hitSlop={8}
            onPress={() => {
              setCursor({ y: today.getFullYear(), m: today.getMonth() });
              setSelected(null);
            }}
          >
            <Feather name="calendar" size={18} color={colors.textSub} />
          </Pressable>
        </View>

        <View style={styles.monthNav}>
          <Pressable onPress={() => move(-1)} hitSlop={12}>
            <Feather name="chevron-left" size={18} color={colors.text} />
          </Pressable>
          <Text style={styles.monthLabel}>
            {cursor.y}년 {cursor.m + 1}월
          </Text>
          <Pressable onPress={() => move(1)} hitSlop={12}>
            <Feather name="chevron-right" size={18} color={colors.text} />
          </Pressable>
        </View>

        <View style={styles.calendar}>
          <View style={styles.week}>
            {WEEKDAYS.map((w) => (
              <Text key={w} style={styles.weekday}>
                {w}
              </Text>
            ))}
          </View>
          {grid.map((week, i) => (
            <View key={i} style={styles.week}>
              {week.map(({ date, inMonth }) => {
                const hasBilling = inMonth && billings.has(date.getDate());
                const isSelected = selected && sameDay(date, selected);
                const isToday = sameDay(date, today);
                return (
                  <Pressable
                    key={date.toISOString()}
                    style={styles.dayCell}
                    disabled={!inMonth}
                    onPress={() => setSelected(isSelected ? null : date)}
                  >
                    <View
                      style={[
                        styles.dayCircle,
                        isToday && styles.today,
                        isSelected && styles.selectedDay,
                      ]}
                    >
                      <Text
                        style={[
                          styles.dayText,
                          !inMonth && { color: colors.textMuted },
                          isSelected && { color: '#fff', fontWeight: '700' },
                        ]}
                      >
                        {date.getDate()}
                      </Text>
                    </View>
                    <View style={[styles.dot, !hasBilling && { opacity: 0 }]} />
                  </Pressable>
                );
              })}
            </View>
          ))}
        </View>

        {subscriptions.length === 0 ? (
          <View style={styles.emptyCard}>
            <View style={styles.emptyTitleRow}>
              <Feather name="bar-chart-2" size={22} color={colors.primary} />
              <Text style={[font.heading, { marginLeft: space.sm }]}>분석할 데이터가 없어요</Text>
            </View>
            <Text style={styles.emptyDesc}>
              {'구독을 추가하고 결제 기록이 쌓이면 지출 패턴\n과 절약 기회를 알려드려요.'}
            </Text>
          </View>
        ) : (
          <View style={{ gap: space.sm }}>
            <View style={styles.listHeader}>
              <Text style={font.label}>
                {selected ? `${selected.getMonth() + 1}월 ${selected.getDate()}일 결제` : `${cursor.m + 1}월 결제 예정`}
              </Text>
              {!selected && <Text style={font.caption}>총 {formatWon(monthTotal)}</Text>}
            </View>
            {list.length === 0 && <Text style={font.caption}>결제 예정인 구독이 없어요.</Text>}
            {list.map(({ s, day }) => {
              // 이 달의 해당 결제일 기준 해지 권장 기간
              const w = cancelWindow(s, new Date(cursor.y, cursor.m, day));
              return (
                <View key={`${s.id}-${day}`} style={styles.row}>
                  <Text style={styles.rowDate}>{day}일</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={font.label}>{s.name}</Text>
                    <Text style={font.caption}>
                      해지 권장 {w.start.getMonth() + 1}/{w.start.getDate()} ~ {w.end.getMonth() + 1}/
                      {w.end.getDate()}
                    </Text>
                  </View>
                  <Text style={font.label}>{formatWon(s.amount)}</Text>
                </View>
              );
            })}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: space.xl, paddingBottom: space.xxl },
  titleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: space.lg,
  },
  monthNav: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: space.xl,
    paddingHorizontal: 2,
  },
  monthLabel: { fontSize: 15, fontWeight: '700', color: colors.text },
  calendar: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    paddingVertical: space.md,
    paddingHorizontal: space.sm,
    marginBottom: space.lg,
  },
  week: { flexDirection: 'row' },
  weekday: { flex: 1, textAlign: 'center', fontSize: 10, color: colors.textSub, paddingBottom: space.sm },
  dayCell: { flex: 1, alignItems: 'center', paddingVertical: 6 },
  dayCircle: { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
  today: { borderWidth: 1, borderColor: colors.primary },
  selectedDay: { backgroundColor: colors.primary, borderColor: colors.primary },
  dayText: { fontSize: 12, color: colors.text },
  dot: { width: 5, height: 5, borderRadius: 3, backgroundColor: colors.primary, marginTop: 3 },
  emptyCard: {
    backgroundColor: colors.primarySoft,
    borderRadius: radius.lg,
    paddingVertical: space.xl,
    alignItems: 'center',
  },
  emptyTitleRow: { flexDirection: 'row', alignItems: 'center' },
  emptyDesc: { fontSize: 12, color: colors.textMuted, textAlign: 'center', lineHeight: 19, marginTop: space.md },
  listHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    padding: space.lg,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
  },
  rowDate: { fontSize: 14, fontWeight: '800', color: colors.primary, width: 36 },
});
