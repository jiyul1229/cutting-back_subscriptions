import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { PrimaryButton } from '@/components/ui';
import { useAppStore } from '@/store/AppStore';
import { colors, font, radius, space } from '@/theme/tokens';

export default function Onboarding() {
  const { completeOnboarding } = useAppStore();

  const start = async () => {
    await completeOnboarding();
    router.replace('/(tabs)');
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.body}>
        <View style={styles.hero}>
          <View style={styles.card}>
            <Text style={font.caption}>이번 달 구독료</Text>
            <Text style={styles.amount}>41,800원</Text>
            <View style={styles.badge}>
              <Text style={styles.badgeText}>이번 달 17,000원 절약</Text>
            </View>
          </View>
        </View>
        <Text style={styles.title}>{'구독은 한눈에,\n절약은 매달 확인해요'}</Text>
        <Text style={[font.body, styles.desc]}>
          {'흩어진 구독을 모아 관리하고, 줄일 수 있는 지출을\nKooD가 알려드려요.'}
        </Text>
      </View>
      <PrimaryButton title="시작하기" onPress={start} style={{ marginHorizontal: space.xl, marginBottom: space.lg }} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  body: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: space.xl },
  hero: {
    width: '85%',
    aspectRatio: 1.07,
    backgroundColor: colors.primarySoft,
    borderRadius: radius.xl,
    alignItems: 'center',
    justifyContent: 'center',
  },
  card: {
    width: '76%',
    backgroundColor: '#fff',
    borderRadius: radius.lg,
    padding: space.xl,
    shadowColor: '#000',
    shadowOpacity: 0.08,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 3,
  },
  amount: { fontSize: 28, fontWeight: '800', color: colors.text, marginVertical: space.md },
  badge: {
    alignSelf: 'flex-start',
    backgroundColor: colors.successSoft,
    borderRadius: radius.pill,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  badgeText: { fontSize: 11, fontWeight: '700', color: colors.success },
  title: { fontSize: 24, fontWeight: '800', color: colors.text, textAlign: 'center', marginTop: 36, lineHeight: 32 },
  desc: { textAlign: 'center', marginTop: space.lg, lineHeight: 21 },
});
