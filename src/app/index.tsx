// 스플래시: 저장소 로딩이 끝나면 온보딩 여부에 따라 분기
import { Feather } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { SecondaryButton } from '@/components/ui';
import { useAppStore } from '@/store/AppStore';
import { colors, font, radius, space } from '@/theme/tokens';

const SPLASH_MS = 1200;

export default function Splash() {
  const { ready, onboarded, loadError, reload } = useAppStore();

  useEffect(() => {
    if (!ready) return;
    const t = setTimeout(() => {
      router.replace(onboarded ? '/(tabs)' : '/onboarding');
    }, SPLASH_MS);
    return () => clearTimeout(t);
  }, [ready, onboarded]);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.center}>
        <View style={styles.logo}>
          <Feather name="credit-card" size={40} color="#fff" />
        </View>
        <Text style={styles.brand}>KooD</Text>
        <Text style={font.body}>가벼워지는 구독 생활에 오신 걸 환영해요</Text>
      </View>
      {loadError ? (
        <View style={styles.error}>
          <Text style={[font.body, styles.errorText]}>{loadError}</Text>
          <SecondaryButton title="다시 시도" onPress={reload} />
        </View>
      ) : (
        <Text style={[font.caption, styles.footer]}>구독 다이어트</Text>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  logo: {
    width: 108,
    height: 108,
    borderRadius: radius.xl + 4,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: colors.primary,
    shadowOpacity: 0.3,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 6,
  },
  brand: { fontSize: 36, fontWeight: '800', color: colors.text, marginTop: 20, marginBottom: 12 },
  footer: { textAlign: 'center', marginBottom: 24 },
  error: { paddingHorizontal: space.xl, marginBottom: space.xxl, gap: space.md },
  errorText: { textAlign: 'center' },
});
