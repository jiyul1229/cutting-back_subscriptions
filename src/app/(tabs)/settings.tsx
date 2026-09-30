import { Feather } from '@expo/vector-icons';
import Constants from 'expo-constants';
import { router } from 'expo-router';
import type { ComponentProps } from 'react';
import { Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from '@/components/ui';
import { useAppStore } from '@/store/AppStore';
import { colors, font, radius, space } from '@/theme/tokens';

const APP_VERSION = Constants.expoConfig?.version ?? '1.0.0';

export default function Settings() {
  const { settings, updateSettings, resetAll } = useAppStore();

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <AppHeader />
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={[font.title, { marginBottom: space.lg }]}>설정</Text>

        <Text style={styles.section}>앱 사용 설정</Text>
        <View style={styles.group}>
          <ToggleRow
            icon="bell"
            title="앱 알림 설정"
            desc="결제 예정일과 구독 변동을 알려드려요"
            value={settings.notifications}
            onChange={(v) => updateSettings({ notifications: v })}
          />
          <View style={styles.divider} />
          <ToggleRow
            icon="zap"
            title="해지 추천 설정"
            desc="사용 패턴을 바탕으로 절약 기회를 추천해요"
            value={settings.recommendations}
            onChange={(v) => updateSettings({ recommendations: v })}
          />
        </View>

        <Text style={[styles.section, { marginTop: space.xxl - 4 }]}>앱 정보</Text>
        <View style={styles.infoRow}>
          <Text style={font.label}>앱 버전</Text>
          <Text style={font.caption}>{APP_VERSION}</Text>
        </View>

        <View style={styles.notice}>
          <Text style={styles.noticeTitle}>내 구독 정보는 안전하게</Text>
          <Text style={styles.noticeBody}>
            KooD는 구독 관리를 위해 필요한 정보만 사용하며, 언제든 설정을 변경할 수 있어요.
          </Text>
        </View>

        {__DEV__ && (
          <Pressable
            style={{ marginTop: space.xxl, alignSelf: 'center' }}
            onPress={async () => {
              await resetAll();
              router.replace('/');
            }}
          >
            <Text style={font.caption}>데이터 초기화 (개발용)</Text>
          </Pressable>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function ToggleRow({
  icon,
  title,
  desc,
  value,
  onChange,
}: {
  icon: ComponentProps<typeof Feather>['name'];
  title: string;
  desc: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <View style={styles.row}>
      <View style={styles.rowIcon}>
        <Feather name={icon} size={16} color={colors.primary} />
      </View>
      <View style={{ flex: 1, marginHorizontal: space.md }}>
        <Text style={font.label}>{title}</Text>
        <Text style={[font.caption, { fontSize: 11, marginTop: 2 }]}>{desc}</Text>
      </View>
      <Switch
        value={value}
        onValueChange={onChange}
        trackColor={{ true: colors.primary, false: colors.border }}
        thumbColor="#fff"
        {...({ activeThumbColor: '#fff' } as object)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: space.xl, paddingTop: space.lg, paddingBottom: space.xxl },
  section: { fontSize: 12, fontWeight: '600', color: colors.textSub, marginBottom: space.sm },
  group: { backgroundColor: colors.surface, borderRadius: radius.lg, paddingHorizontal: space.lg },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.lg },
  rowIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.sm,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  divider: { height: 1, backgroundColor: colors.border },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  notice: {
    backgroundColor: colors.primarySoft,
    borderRadius: radius.lg,
    padding: space.lg,
    marginTop: space.xl,
  },
  noticeTitle: { fontSize: 13, fontWeight: '700', color: colors.primary, marginBottom: 6 },
  noticeBody: { fontSize: 11, color: colors.textSub, lineHeight: 17 },
});
