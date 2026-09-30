import { router } from 'expo-router';
import { Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader, SecondaryButton } from '@/components/ui';
import { useAppStore } from '@/store/AppStore';
import { colors, font, space } from '@/theme/tokens';

export default function Settings() {
  const { resetAll } = useAppStore();
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['top']}>
      <AppHeader />
      <View style={{ padding: space.xl }}>
        <Text style={[font.title, { marginBottom: space.lg }]}>설정</Text>
        {/* 개발용: 데이터·온보딩 초기화 */}
        <SecondaryButton
          title="데이터 초기화 (개발용)"
          onPress={async () => {
            await resetAll();
            router.replace('/');
          }}
        />
      </View>
    </SafeAreaView>
  );
}
