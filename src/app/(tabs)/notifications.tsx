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

// 알림 종류별 아이콘 매핑 (시안 감성 반영)
const KIND_ICON: Record<NotificationKind, ComponentProps<typeof Feather>['name']> = {
  billing: 'bell',       // 결제일 알림은 종 모양
  cancelWindow: 'zap',   // 해지 추천은 번개/스파크 모양
  lowUsage: 'zap',       // 저이용 알림도 번개 모양
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
          <Text style={[font.caption, { marginTop: space.md, textAlign: 'center' }]}>
            결제 알림 및 해지 추천 알림이 생기면{'\n'}이곳에 카드로 표시돼요.
          </Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.list}>
          <Text style={[font.title, { marginBottom: space.sm }]}>알림</Text>
          {items.map((n) => {
            const isBilling = n.kind === 'billing';

            return (
              <View key={n.id} style={styles.notificationCard}>
                {/* 좌측 아이콘 박스: 결제일은 주황/연빨강, 해지추천은 노랑/오렌지 계열 배경 */}
                <View style={[styles.iconBox, isBilling ? styles.billingIconBg : styles.recommendIconBg]}>
                  <Feather
                    name={KIND_ICON[n.kind]}
                    size={18}
                    color={isBilling ? '#FF5722' : '#FF9500'}
                  />
                </View>

                {/* 우측 텍스트 내용 */}
                <View style={{ flex: 1, marginLeft: space.md }}>
                  <Text style={styles.notifTitle}>{n.title}</Text>
                  <Text style={styles.notifBody}>{n.body}</Text>
                </View>
              </View>
            );
          })}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingBottom: 40, paddingHorizontal: space.xl },
  emptyIcon: {
    width: 78,
    height: 78,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  list: { padding: space.xl, gap: space.md },
  
  // 시안 스타일을 반영한 고급스러운 알림 카드 스타일
  notificationCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  iconBox: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  billingIconBg: {
    backgroundColor: '#FFE5E6', // 결제일 알림 배경 (연한 레드/오렌지)
  },
  recommendIconBg: {
    backgroundColor: '#FFF4E5', // 해지 추천 알림 배경 (연한 옐로/오렌지)
  },
  notifTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.text,
    marginBottom: 2,
  },
  notifBody: {
    fontSize: 12,
    color: colors.textSub,
    lineHeight: 17,
  },
});