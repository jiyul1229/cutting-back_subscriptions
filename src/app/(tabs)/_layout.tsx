import { Feather } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import type { ComponentProps } from 'react';
import type { ColorValue } from 'react-native';
import { colors } from '@/theme/tokens';

type IconName = ComponentProps<typeof Feather>['name'];

const icon =
  (name: IconName) =>
  ({ color }: { color: ColorValue }) => <Feather name={name} size={20} color={color as string} />;

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarLabelStyle: { fontSize: 11 },
        tabBarStyle: { borderTopColor: colors.border },
        sceneStyle: { backgroundColor: colors.bg },
      }}
    >
      <Tabs.Screen name="index" options={{ title: '홈', tabBarIcon: icon('home') }} />
      <Tabs.Screen name="calendar" options={{ title: '캘린더', tabBarIcon: icon('calendar') }} />
      <Tabs.Screen name="analysis" options={{ title: '분석', tabBarIcon: icon('bar-chart-2') }} />
      <Tabs.Screen name="settings" options={{ title: '설정', tabBarIcon: icon('settings') }} />
    </Tabs>
  );
}
