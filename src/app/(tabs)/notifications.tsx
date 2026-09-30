// 알림 — 헤더 종 아이콘으로 진입. 탭바에는 노출하지 않음 (_layout에서 href: null)
import { Feather } from '@expo/vector-icons';
import type { ComponentProps } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from '@/components/ui';
import { buildNotifications } from '@/domain/engine';
import type { NotificationKind } from '@/domain/types';
import { useAppStore } from '@/store/AppStore';
import { colors, font, radius, space } from '@/theme/tokens';

const KIND_ICON: Record<NotificationKind, ComponentProps<typeof Feather>['name']> = {
  billing: 'credit-card',
  cancelWindow: 'calendar',
  lowUsage: 'zap',
};

export default function Notifications() {
  const { subscriptions, usageLogs, settings } = useAppStore();
  const items = buildNotifications(subscriptions, usageLogs, settings);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <AppHeader />
      {items.length === 0 ? (
        <View style={styles.empty}>
          <View style={styles.emptyIcon}>
            <Feather name="bell" size={30} color={colors.primary} />
          </View>
          <Text style={[font.heading, { marginTop: space.lg }]}>수신한 알림이 없어요</Text>
          <Text style={[font.caption, { marginTop: space.md }]}>
            결제 알림 및 해지 추천 알림을 띄워줘요.
          </Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.list}>
          <Text style={[font.title, { marginBottom: space.sm }]}>알림</Text>
          {items.map((n) => (
            <View key={n.id} style={styles.row}>
              <View style={styles.rowIcon}>
                <Feather name={KIND_ICON[n.kind]} size={16} color={colors.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={font.label}>{n.title}</Text>
                <Text style={[font.caption, { marginTop: 2, lineHeight: 17 }]}>{n.body}</Text>
              </View>
            </View>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingBottom: 40 },
  emptyIcon: {
    width: 78,
    height: 78,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  list: { padding: space.xl, gap: space.md },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: space.md,
    padding: space.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  rowIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.sm,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
