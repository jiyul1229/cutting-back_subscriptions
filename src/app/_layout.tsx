import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { AppStoreProvider } from '@/store/AppStore';

export default function RootLayout() {
  return (
    <AppStoreProvider>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: '#fff' } }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="onboarding" options={{ animation: 'fade' }} />
        <Stack.Screen name="(tabs)" options={{ animation: 'fade' }} />
        <Stack.Screen name="subscription/new" options={{ presentation: 'modal' }} />
        {/* 아래 코드를 추가하여 구독 수정 페이지 라우트를 등록합니다 */}
        <Stack.Screen name="subscription/edit" options={{ presentation: 'modal' }} />
      </Stack>
    </AppStoreProvider>
  );
}